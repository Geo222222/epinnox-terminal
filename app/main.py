from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .backtest import run_backtest
from .live_intelligence import live_intelligence
from .market import TIMEFRAME_SPECS, cache_stats, fetch_ohlcv, fetch_ohlcv_range, symbols
from .models import BacktestRequest, PaperLiveStartRequest, ScannerRequest
from .online_bridge import (
    OnlineBridgeError,
    account_snapshot as online_account_snapshot,
    activate_account as online_activate_account,
    list_accounts as online_list_accounts,
    paper_state as online_paper_state,
)
from .perf import run_compute
from .presets import PRESETS, STRATEGIES, preset_source
from .scan_store import scan_store
from .scanner import run_scanner
from .session_registry import SessionConflict, SessionNotFound, paper_sessions
from .settings import public_settings
from .storage import ACTIVE_SESSION_STATUSES, runtime_store

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
logger = logging.getLogger("epinnox.terminal")

TIMEFRAMES = list(TIMEFRAME_SPECS)
TIMEFRAME_LABELS = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "5h": "5h", "8h": "8h",
    "1d": "D", "5d": "5D", "1w": "W", "1M": "M",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    live_enabled = os.getenv("EPINNOX_DISABLE_LIVE_INTELLIGENCE", "0") != "1"
    if live_enabled:
        live_intelligence.start()
    try:
        yield
    finally:
        if live_enabled:
            live_intelligence.shutdown()
        await paper_sessions.shutdown()


app = FastAPI(title="Epinnox Terminal", version="0.8.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")


def _online_base() -> str | None:
    return os.getenv("EPINNOX_ONLINE_BASE_URL")


def _cookie(request: Request) -> str:
    return request.headers.get("cookie", "")


def _raise_bridge(exc: OnlineBridgeError) -> None:
    status_code = exc.status_code if exc.status_code in {400, 401, 403, 404, 409, 422, 429, 503} else 502
    raise HTTPException(status_code=status_code, detail=exc.detail) from exc


async def _account_rows(request: Request) -> list[dict[str, Any]]:
    try:
        return await online_list_accounts(_online_base(), _cookie(request))
    except OnlineBridgeError as exc:
        _raise_bridge(exc)
    return []


def _find_account(rows: list[dict[str, Any]], account_id: str) -> dict[str, Any] | None:
    return next((row for row in rows if str(row.get("id") or "") == account_id), None)


def _run_backtest_request(req: BacktestRequest) -> dict[str, Any]:
    settings = public_settings()
    max_range_bars = int(settings["backtest_defaults"].get("max_range_bars", 50000))
    if req.start_ts_ms is not None and req.end_ts_ms is not None:
        candles = fetch_ohlcv_range(req.symbol, req.timeframe, req.start_ts_ms, req.end_ts_ms, max_bars=max_range_bars)
    else:
        candles = fetch_ohlcv(req.symbol, req.timeframe, req.limit)
    if not candles:
        raise ValueError("No candles returned for the requested backtest window")
    return {"candles": candles, **run_backtest(candles, req)}


def _latest_session_snapshot() -> dict[str, Any] | None:
    rows = paper_sessions.list(100)
    active = [row for row in rows if row.get("status") in ACTIVE_SESSION_STATUSES]
    return active[0] if active else (rows[0] if rows else None)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/scanner")
def scanner_page():
    return FileResponse(WEB / "scanner.html")


@app.get("/sessions")
def sessions_page():
    return FileResponse(WEB / "sessions.html")


@app.get("/research")
def research_page():
    return FileResponse(WEB / "research.html")


@app.get("/strategies")
def strategies_page():
    return FileResponse(WEB / "strategies.html")


@app.get("/api/health")
def health():
    active = paper_sessions.active()
    return {
        "ok": True,
        "service": "epinnox-terminal",
        "version": app.version,
        "market_cache": cache_stats(),
        "live_intelligence": live_intelligence.status(),
        "paper_sessions": {"active": len(active), "running_in_process": sum(1 for x in active if x.get("running"))},
        "epinnox_online_configured": bool(_online_base()),
    }


@app.get("/api/config")
def config():
    settings = public_settings()
    terminal = settings["terminal"]
    return {
        "schema_version": settings["schema_version"],
        "strategies": STRATEGIES,
        "timeframes": TIMEFRAMES,
        "timeframe_labels": TIMEFRAME_LABELS,
        "timeframe_preset_source": {tf: preset_source(tf) for tf in TIMEFRAMES},
        "presets": PRESETS,
        "confirmation_policies": ["Single", "All Recent Events", "Quorum Recent Events", "Primary + All States"],
        "backtest_profiles": ["TradingView Parity", "Simplified Isolated"],
        "scanner_objectives": ["Capital Growth", "Break-Even Throughput"],
        "default_symbol": terminal["default_symbol"],
        "defaults": settings,
        "live_intelligence": live_intelligence.status(),
        "execution": {
            "epinnox_online_base_url": _online_base(),
            "paper_live_adapter_configured": bool(_online_base()),
            "account_context": "epinnox-online-session",
            "live_order_routing_armed": False,
            "multi_session": True,
            "multi_account_concurrency": False,
            "ownership_rule": "one active strategy owner per account + instrument",
        },
    }


@app.get("/api/settings")
def settings():
    return public_settings()


@app.get("/api/settings/presets")
def list_named_presets():
    return {"schema_version": 1, "presets": runtime_store.list_presets()}


@app.post("/api/settings/presets")
def save_named_preset(payload: dict[str, Any] = Body(...)):
    name = str(payload.get("name") or "").strip()
    values = payload.get("payload")
    schema_version = int(payload.get("schema_version") or 1)
    if not name or len(name) > 80:
        raise HTTPException(400, "Preset name is required and must be at most 80 characters")
    if not isinstance(values, dict):
        raise HTTPException(400, "Preset payload must be an object")
    if schema_version != 1:
        raise HTTPException(400, "Unsupported preset schema_version")
    return runtime_store.save_preset(name, values, schema_version)


@app.delete("/api/settings/presets/{name}")
def delete_named_preset(name: str):
    if not runtime_store.delete_preset(name):
        raise HTTPException(404, "Preset not found")
    return {"deleted": True, "name": name}


@app.get("/api/symbols")
async def list_symbols():
    try:
        return {"symbols": await run_compute(symbols)}
    except Exception as exc:
        logger.exception("symbol load failed")
        raise HTTPException(502, f"HTX symbol load failed: {exc}") from exc


@app.get("/api/live/status")
def live_status():
    return live_intelligence.status()


@app.get("/api/live/universe")
def live_universe():
    return live_intelligence.universe_snapshot()


@app.post("/api/live/control")
def live_control(payload: dict[str, Any] = Body(...)):
    allowed = {"universe_enabled", "scanner_enabled", "pause_all"}
    unknown = set(payload) - allowed
    if unknown:
        raise HTTPException(400, f"Unsupported live-control fields: {', '.join(sorted(unknown))}")
    universe = payload.get("universe_enabled")
    scanner = payload.get("scanner_enabled")
    if "pause_all" in payload:
        enabled = not bool(payload["pause_all"])
        universe = enabled
        scanner = enabled
    return live_intelligence.set_controls(universe_enabled=universe, scanner_enabled=scanner)


@app.post("/api/live/mandate")
def live_mandate(payload: dict[str, Any] = Body(...)):
    try:
        return live_intelligence.update_mandate(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/market")
async def market(symbol: str = Query("ETH/USDT:USDT"), timeframe: str = Query("1m"), limit: int = Query(1000, ge=100, le=50000)):
    try:
        candles = await run_compute(fetch_ohlcv, symbol, timeframe, limit)
        return {"symbol": symbol, "timeframe": timeframe, "candles": candles, "source": "HTX via CCXT"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("market load failed symbol=%s timeframe=%s", symbol, timeframe)
        raise HTTPException(502, f"HTX OHLCV failed: {exc}") from exc


@app.post("/api/backtest")
async def backtest(req: BacktestRequest):
    try:
        return await run_compute(_run_backtest_request, req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("backtest failed symbol=%s timeframe=%s strategy=%s", req.symbol, req.timeframe, req.strategy)
        raise HTTPException(502, f"Backtest failed: {exc}") from exc


@app.post("/api/scanner/run")
async def scanner_run(req: ScannerRequest):
    """One-shot scanner API retained for deterministic external experiments.

    Product UI uses the continuous Live Scanner runtime. This endpoint remains
    an explicit research primitive rather than a second competing UI lifecycle.
    """
    try:
        result = await run_compute(run_scanner, req)
        scan_store.save(result)
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("scanner failed objective=%s", req.objective)
        raise HTTPException(502, f"Opportunity scan failed: {exc}") from exc


@app.get("/api/scanner/runs")
def scanner_runs(limit: int = Query(20, ge=1, le=100)):
    return {"schema_version": 1, "runs": scan_store.recent(limit)}


@app.get("/api/scanner/runs/{scan_id}")
def scanner_run_detail(scan_id: str):
    result = scan_store.get(scan_id)
    if result is None:
        raise HTTPException(404, "Scan not found")
    return result


@app.get("/api/execution/accounts")
async def execution_accounts(request: Request):
    if not _online_base():
        return {"configured": False, "authenticated": False, "accounts": [], "active_account_id": None}
    rows = await _account_rows(request)
    active = next((str(row.get("id")) for row in rows if row.get("is_active")), None)
    return {"configured": True, "authenticated": True, "accounts": rows, "active_account_id": active}


@app.post("/api/execution/accounts/{account_id}/activate")
async def activate_execution_account(account_id: str, request: Request, mode: Literal["paper", "live"] = Query(...)):
    rows = await _account_rows(request)
    row = _find_account(rows, account_id)
    if row is None:
        raise HTTPException(404, "Account not found in the authenticated Epinnox Online session")
    account_mode = str(row.get("account_mode") or "").lower()
    if account_mode != mode:
        raise HTTPException(409, f"Selected account is {account_mode or 'unknown'}, not {mode}")
    if mode == "paper":
        running_accounts = {str(x.get("account_id")) for x in paper_sessions.active() if x.get("running")}
        if running_accounts and account_id not in running_accounts:
            raise HTTPException(
                409,
                "Another paper account currently owns the Epinnox Online execution context. Stop or recover those sessions before switching accounts.",
            )
    try:
        result = await online_activate_account(_online_base(), _cookie(request), account_id)
    except OnlineBridgeError as exc:
        _raise_bridge(exc)
    refreshed = await _account_rows(request)
    active = _find_account(refreshed, account_id)
    if not active or not active.get("is_active"):
        raise HTTPException(409, "Epinnox Online did not confirm the selected account as active")
    return {"ok": True, "account": active, "activation": result}


@app.get("/api/execution/accounts/{account_id}/state")
async def execution_account_state(account_id: str, request: Request):
    rows = await _account_rows(request)
    row = _find_account(rows, account_id)
    if row is None:
        raise HTTPException(404, "Account not found in the authenticated Epinnox Online session")
    if not row.get("is_active"):
        return {"account": row, "active": False, "state": None}
    try:
        if str(row.get("account_mode") or "").lower() == "paper":
            state = await online_paper_state(_online_base(), _cookie(request))
        else:
            state = await online_account_snapshot(_online_base(), _cookie(request))
    except OnlineBridgeError as exc:
        _raise_bridge(exc)
    return {"account": row, "active": True, "state": state}


@app.get("/api/sessions")
def list_sessions(limit: int = Query(100, ge=1, le=1000)):
    return {"schema_version": 1, "sessions": paper_sessions.list(limit)}


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: str):
    try:
        return paper_sessions.get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/sessions/paper/start")
async def start_paper_session(req: PaperLiveStartRequest, request: Request):
    try:
        return await paper_sessions.start(
            req.strategy,
            _online_base(),
            _cookie(request),
            account_id=req.account_id,
            name=req.name,
        )
    except SessionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.exception("paper session start failed account=%s symbol=%s", req.account_id, req.strategy.symbol)
        raise HTTPException(502, f"Paper session start failed: {exc}") from exc


@app.post("/api/sessions/{session_id}/recover")
async def recover_session(session_id: str, request: Request):
    try:
        return await paper_sessions.recover(session_id, _online_base(), _cookie(request))
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except SessionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Paper recovery failed: {exc}") from exc


@app.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    try:
        return await paper_sessions.stop(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/execution/status")
def execution_status():
    base = _online_base()
    active = paper_sessions.active()
    latest = _latest_session_snapshot()
    return {
        "backtest": "ready",
        "scanner": live_intelligence.status()["scanner"]["state"].lower(),
        "paper": "ready" if base else "not-configured",
        "live": "account-selection-ready",
        "live_order_routing": "not-armed",
        "paper_running": bool(latest and latest.get("running")),
        "paper_status": None if latest is None else latest.get("status"),
        "paper_session_id": None if latest is None else latest.get("session_id"),
        "paper_account_id": None if latest is None else latest.get("account_id"),
        "paper_sessions_active": len(active),
        "paper_sessions_running": sum(1 for x in active if x.get("running")),
        "multi_session": True,
        "multi_account_concurrency": False,
        "epinnox_online_base_url": base,
        "note": (
            "PAPER supports multiple durable strategy sessions on the same active Epinnox Online paper account, "
            "with one strategy owner per account + instrument. Multi-account concurrency remains fail-closed until upstream execution is account-scoped."
        ),
    }


# Compatibility routes for the existing frontend. V4 uses /api/sessions/* directly.
@app.post("/api/paper-live/start")
async def start_paper_live(req: PaperLiveStartRequest, request: Request):
    return await start_paper_session(req, request)


@app.post("/api/paper-live/recover")
async def recover_paper_live(request: Request):
    active = paper_sessions.active()
    if not active:
        latest = _latest_session_snapshot()
        if latest is None:
            return {"status": "STOPPED", "running": False, "session_id": None}
        active = [latest]
    if len(active) != 1:
        raise HTTPException(409, "Multiple paper sessions exist; recover a specific session through /api/sessions/{session_id}/recover")
    return await recover_session(str(active[0]["session_id"]), request)


@app.post("/api/paper-live/stop")
async def stop_paper_live():
    active = paper_sessions.active()
    if not active:
        latest = _latest_session_snapshot()
        return latest or {"status": "STOPPED", "running": False, "session_id": None}
    if len(active) != 1:
        raise HTTPException(409, "Multiple paper sessions exist; stop a specific session through /api/sessions/{session_id}/stop")
    return await stop_session(str(active[0]["session_id"]))


@app.get("/api/paper-live/status")
def paper_live_status():
    return _latest_session_snapshot() or {"status": "STOPPED", "running": False, "session_id": None, "events": []}

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .backtest import run_backtest
from .market import TIMEFRAME_SPECS, fetch_ohlcv, fetch_ohlcv_range, symbols
from .models import BacktestRequest, PaperLiveStartRequest, ScannerRequest
from .online_bridge import (
    OnlineBridgeError,
    account_snapshot as online_account_snapshot,
    activate_account as online_activate_account,
    list_accounts as online_list_accounts,
    paper_state as online_paper_state,
)
from .paper_live import PaperLiveManager
from .presets import PRESETS, STRATEGIES, preset_source
from .scan_store import scan_store
from .scanner import run_scanner
from .settings import public_settings
from .storage import runtime_store

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
paper_live = PaperLiveManager()

TIMEFRAMES = list(TIMEFRAME_SPECS)
TIMEFRAME_LABELS = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "5h": "5h", "8h": "8h",
    "1d": "D", "5d": "5D", "1w": "W", "1M": "M",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    await paper_live.recover(os.getenv("EPINNOX_ONLINE_BASE_URL"))
    yield
    await paper_live.shutdown()


app = FastAPI(title="Epinnox Terminal", version="0.6.0", lifespan=lifespan)
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


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/scanner")
def scanner_page():
    return FileResponse(WEB / "scanner.html")


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
        "confirmation_policies": [
            "Single",
            "All Recent Events",
            "Quorum Recent Events",
            "Primary + All States",
        ],
        "backtest_profiles": [
            "TradingView Parity",
            "Simplified Isolated",
        ],
        "scanner_objectives": ["Capital Growth", "Break-Even Throughput"],
        "default_symbol": terminal["default_symbol"],
        "defaults": settings,
        "execution": {
            "epinnox_online_base_url": _online_base(),
            "paper_live_adapter_configured": bool(_online_base()),
            "account_context": "epinnox-online-session",
            "live_order_routing_armed": False,
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
def list_symbols():
    try:
        return {"symbols": symbols()}
    except Exception as exc:
        raise HTTPException(502, f"HTX symbol load failed: {exc}") from exc


@app.get("/api/market")
def market(symbol: str = Query("ETH/USDT:USDT"), timeframe: str = Query("1m"), limit: int = Query(1000, ge=100, le=50000)):
    try:
        candles = fetch_ohlcv(symbol, timeframe, limit)
        return {"symbol": symbol, "timeframe": timeframe, "candles": candles, "source": "HTX via CCXT"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"HTX OHLCV failed: {exc}") from exc


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    try:
        settings = public_settings()
        max_range_bars = int(settings["backtest_defaults"].get("max_range_bars", 50000))
        if req.start_ts_ms is not None and req.end_ts_ms is not None:
            candles = fetch_ohlcv_range(
                req.symbol,
                req.timeframe,
                req.start_ts_ms,
                req.end_ts_ms,
                max_bars=max_range_bars,
            )
        else:
            candles = fetch_ohlcv(req.symbol, req.timeframe, req.limit)
        if not candles:
            raise ValueError("No candles returned for the requested backtest window")
        return {"candles": candles, **run_backtest(candles, req)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Backtest failed: {exc}") from exc


@app.post("/api/scanner/run")
def scanner_run(req: ScannerRequest):
    try:
        result = run_scanner(req)
        scan_store.save(result)
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
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
async def activate_execution_account(
    account_id: str,
    request: Request,
    mode: Literal["paper", "live"] = Query(...),
):
    rows = await _account_rows(request)
    row = _find_account(rows, account_id)
    if row is None:
        raise HTTPException(404, "Account not found in the authenticated Epinnox Online session")
    account_mode = str(row.get("account_mode") or "").lower()
    if account_mode != mode:
        raise HTTPException(409, f"Selected account is {account_mode or 'unknown'}, not {mode}")
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


@app.get("/api/execution/status")
def execution_status():
    base = _online_base()
    return {
        "backtest": "ready",
        "scanner": "ready",
        "paper": "ready" if base else "not-configured",
        "live": "account-selection-ready",
        "live_order_routing": "not-armed",
        "paper_running": paper_live.state.running,
        "paper_status": paper_live.state.status,
        "paper_session_id": paper_live.state.session_id,
        "paper_account_id": paper_live.state.account_id,
        "epinnox_online_base_url": base,
        "note": (
            "PAPER is bound to an explicit Epinnox Online paper account and fails closed if that account context changes. "
            "LIVE account selection is wired, but real order routing remains intentionally unarmed."
        ),
    }


@app.post("/api/paper-live/start")
async def start_paper_live(req: PaperLiveStartRequest, request: Request):
    try:
        if paper_live.state.running:
            raise RuntimeError("A paper live session is already running")
        result = await paper_live.start(
            req.strategy,
            _online_base(),
            _cookie(request),
            account_id=req.account_id,
        )
        if result.get("session_id"):
            runtime_store.supersede_active_sessions(keep_session_id=result["session_id"])
        return result
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Paper live start failed: {exc}") from exc


@app.post("/api/paper-live/recover")
async def recover_paper_live(request: Request):
    try:
        return await paper_live.recover(
            _online_base(),
            _cookie(request),
        )
    except Exception as exc:
        raise HTTPException(502, f"Paper recovery failed: {exc}") from exc


@app.post("/api/paper-live/stop")
async def stop_paper_live():
    return await paper_live.stop()


@app.get("/api/paper-live/status")
def paper_live_status():
    return paper_live.snapshot()

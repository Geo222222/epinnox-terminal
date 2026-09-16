from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .backtest import run_backtest
from .market import fetch_ohlcv, fetch_ohlcv_range, symbols
from .models import BacktestRequest
from .paper_live import PaperLiveManager
from .presets import PRESETS, STRATEGIES
from .settings import public_settings
from .storage import runtime_store

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
paper_live = PaperLiveManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await paper_live.recover(os.getenv("EPINNOX_ONLINE_BASE_URL"))
    yield
    await paper_live.shutdown()


app = FastAPI(title="Epinnox Terminal", version="0.4.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
def config():
    settings = public_settings()
    terminal = settings["terminal"]
    return {
        "schema_version": settings["schema_version"],
        "strategies": STRATEGIES,
        "timeframes": ["1m", "5m", "15m", "30m"],
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
        "default_symbol": terminal["default_symbol"],
        "defaults": settings,
        "execution": {
            "epinnox_online_base_url": os.getenv("EPINNOX_ONLINE_BASE_URL"),
            "paper_live_adapter_configured": bool(os.getenv("EPINNOX_ONLINE_BASE_URL")),
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


@app.get("/api/execution/status")
def execution_status():
    base = os.getenv("EPINNOX_ONLINE_BASE_URL")
    return {
        "backtest": "ready",
        "paper": "ready" if base else "not-configured",
        "live": "not-armed",
        "paper_running": paper_live.state.running,
        "paper_status": paper_live.state.status,
        "paper_session_id": paper_live.state.session_id,
        "epinnox_online_base_url": base,
        "note": (
            "PAPER uses durable SQLite checkpoints and reconciles epinnox-online on restart. "
            "LIVE remains intentionally unarmed."
        ),
    }


@app.post("/api/paper-live/start")
async def start_paper_live(req: BacktestRequest, request: Request):
    try:
        if paper_live.state.running:
            raise RuntimeError("A paper live session is already running")
        result = await paper_live.start(
            req,
            os.getenv("EPINNOX_ONLINE_BASE_URL"),
            request.headers.get("cookie", ""),
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
            os.getenv("EPINNOX_ONLINE_BASE_URL"),
            request.headers.get("cookie", ""),
        )
    except Exception as exc:
        raise HTTPException(502, f"Paper recovery failed: {exc}") from exc


@app.post("/api/paper-live/stop")
async def stop_paper_live():
    return await paper_live.stop()


@app.get("/api/paper-live/status")
def paper_live_status():
    return paper_live.snapshot()

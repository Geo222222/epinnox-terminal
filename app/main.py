from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .backtest import run_backtest
from .market import fetch_ohlcv, symbols
from .models import BacktestRequest
from .paper_live import PaperLiveManager
from .presets import PRESETS, STRATEGIES

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

app = FastAPI(title="Epinnox Terminal", version="0.2.0")
app.mount("/static", StaticFiles(directory=WEB), name="static")
paper_live = PaperLiveManager()


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
def config():
    return {
        "strategies": STRATEGIES,
        "timeframes": ["1m", "5m", "15m", "30m"],
        "presets": PRESETS,
        "confirmation_policies": [
            "Single",
            "All Recent Events",
            "Quorum Recent Events",
            "Primary + All States",
        ],
        "default_symbol": "ETH/USDT:USDT",
        "execution": {
            "epinnox_online_base_url": os.getenv("EPINNOX_ONLINE_BASE_URL"),
            "paper_live_adapter_configured": bool(os.getenv("EPINNOX_ONLINE_BASE_URL")),
        },
    }


@app.get("/api/symbols")
def list_symbols():
    try:
        return {"symbols": symbols()}
    except Exception as exc:
        raise HTTPException(502, f"HTX symbol load failed: {exc}") from exc


@app.get("/api/market")
def market(symbol: str = Query("ETH/USDT:USDT"), timeframe: str = Query("1m"), limit: int = Query(1000, ge=100, le=5000)):
    try:
        candles = fetch_ohlcv(symbol, timeframe, limit)
        return {"symbol": symbol, "timeframe": timeframe, "candles": candles, "source": "HTX via CCXT"}
    except Exception as exc:
        raise HTTPException(502, f"HTX OHLCV failed: {exc}") from exc


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    try:
        candles = fetch_ohlcv(req.symbol, req.timeframe, req.limit)
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
        "epinnox_online_base_url": base,
        "note": (
            "PAPER can run the same composite strategy against live HTX candles and routes mutations through "
            "epinnox-online only after its paper-state preflight succeeds. LIVE remains intentionally unarmed."
        ),
    }


@app.post("/api/paper-live/start")
async def start_paper_live(req: BacktestRequest, request: Request):
    try:
        return await paper_live.start(
            req,
            os.getenv("EPINNOX_ONLINE_BASE_URL"),
            request.headers.get("cookie", ""),
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Paper live start failed: {exc}") from exc


@app.post("/api/paper-live/stop")
async def stop_paper_live():
    return await paper_live.stop()


@app.get("/api/paper-live/status")
def paper_live_status():
    return paper_live.snapshot()

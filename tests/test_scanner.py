from pathlib import Path

from app.models import ScannerRequest
from app.scan_store import ScanStore
from app.scanner import _candidate, fee_floor_pct


def candles(n=600):
    out=[]
    px=2500.0
    for i in range(n):
        phase=(i//30)%4
        drift=(3.5 if phase in {0,3} else -3.0)
        op=px
        cl=max(100.0,px+drift)
        hi=max(op,cl)+4.5
        lo=min(op,cl)-4.5
        out.append({"ts_ms":1_700_000_000_000+i*60_000,"open":op,"high":hi,"low":lo,"close":cl,"volume":100+i%9})
        px=cl
    return out


def test_fee_floor_is_deterministic_and_covers_two_sided_fees():
    floor=fee_floor_pct(0.05,0.05,0.0)
    assert floor["long_pct"] > 0.10
    assert floor["short_pct"] > 0.09
    assert abs(floor["long_pct"]-floor["short_pct"]) < 0.001


def test_scanner_candidate_exposes_qualification_and_walk_forward():
    req=ScannerRequest(
        symbols=["ETH/USDT:USDT"],
        timeframes=["1m"],
        strategies=["Supertrend"],
        target_buffers_pct=[0.0],
        history_bars=600,
        walk_forward_windows=3,
        min_sample_trades=1,
        min_walk_forward_pass_rate_pct=0,
        max_drawdown_pct=100,
        min_net_expectancy_usdt=-100000,
        starting_balance=10000,
    )
    row=_candidate(req,candles(),"ETH/USDT:USDT","1m","Supertrend",0.0)
    assert row["symbol"]=="ETH/USDT:USDT"
    assert row["target_buffer_pct"]==0.0
    assert row["fee_floor_long_pct"]>0
    assert row["walk_forward"]["windows"]==3
    assert "qualified" in row
    assert "trades_per_day" in row
    assert "referral_revenue_per_day" in row


def test_scanner_request_caps_excessive_cartesian_work():
    try:
        ScannerRequest(
            symbols=[f"S{i}/USDT:USDT" for i in range(12)],
            timeframes=["1m","5m","15m","30m"],
            strategies=[f"X{i}" for i in range(15)],
            target_buffers_pct=[i/1000 for i in range(12)],
        )
        assert False,"expected oversized scanner request to fail"
    except ValueError:
        pass


def test_scan_store_round_trip(tmp_path: Path):
    store=ScanStore(tmp_path/"scanner.db")
    result={
        "scan_id":"scan-1",
        "objective":"Break-Even Throughput",
        "started_at_ms":1,
        "completed_at_ms":2,
        "request":{"symbols":["ETH/USDT:USDT"]},
        "summary":{"evaluated":1,"qualified":1},
        "results":[{"symbol":"ETH/USDT:USDT","qualified":True}],
    }
    store.save(result)
    assert store.get("scan-1")["objective"]=="Break-Even Throughput"
    recent=store.recent()
    assert recent[0]["summary"]["qualified"]==1

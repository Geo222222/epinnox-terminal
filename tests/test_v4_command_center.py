from pathlib import Path

from app.session_registry import PaperSessionRegistry
from app.storage import RuntimeStore

ROOT = Path(__file__).resolve().parents[1]


def test_v4_command_center_assets_present():
    js = (ROOT / "web" / "v4-command-center.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "v4-command-center.css").read_text(encoding="utf-8")
    shell = (ROOT / "web" / "v4-shell.js").read_text(encoding="utf-8")

    for token in ["OPPORTUNITY SCANNER", "epinnox:session-selected", "/api/scanner/run", "showScanner", "focusSession"]:
        assert token in js
    assert "/static/v4-command-center.js" in shell
    assert ".scanner-workspace-v4" in css
    assert ".session-context-card" in css


def test_session_snapshots_include_exact_strategy_request(tmp_path: Path):
    store = RuntimeStore(tmp_path / "sessions.db")
    store.save_session(
        "paper-1",
        status="RUNNING",
        request={
            "symbol": "ETH/USDT:USDT",
            "timeframe": "5m",
            "strategy": "RSI Mean Reversion",
            "leverage": 3,
            "desired_net_profit_pct": 0.02,
            "_terminal_account_id": "acct-a",
            "_terminal_session_name": "ETH research",
        },
        started_at_ms=1,
        last_bar_ts_ms=None,
        last_error=None,
        last_signal=None,
        position=None,
        layers=0,
        bars_in_position=0,
        pending_intent=None,
    )
    row = PaperSessionRegistry(store).get("paper-1")
    assert row["account_id"] == "acct-a"
    assert row["name"] == "ETH research"
    assert row["request"]["symbol"] == "ETH/USDT:USDT"
    assert row["request"]["strategy"] == "RSI Mean Reversion"
    assert row["request"]["desired_net_profit_pct"] == 0.02
    assert "_terminal_account_id" not in row["request"]

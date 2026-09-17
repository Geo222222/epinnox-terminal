from app import market


def _swap(symbol: str, *, active: bool = True, quote: str = "USDT", linear: bool = True) -> dict:
    base = symbol.split("/")[0]
    return {
        "symbol": symbol,
        "id": symbol.replace("/", "").replace(":", ""),
        "base": base,
        "quote": quote,
        "swap": True,
        "linear": linear,
        "active": active,
        "contractSize": 1.0,
    }


def test_symbols_returns_complete_active_linear_usdt_swap_catalog(monkeypatch):
    preferred = [
        "ETH/USDT:USDT",
        "BTC/USDT:USDT",
        "DOGE/USDT:USDT",
        "SOL/USDT:USDT",
        "XRP/USDT:USDT",
    ]
    markets = {symbol: _swap(symbol) for symbol in preferred}
    markets.update({
        f"ASSET{i:03d}/USDT:USDT": _swap(f"ASSET{i:03d}/USDT:USDT")
        for i in range(300)
    })

    # These venue markets must never leak into the perpetual research universe.
    markets["INACTIVE/USDT:USDT"] = _swap("INACTIVE/USDT:USDT", active=False)
    markets["INVERSE/USDT:USDT"] = _swap("INVERSE/USDT:USDT", linear=False)
    markets["BTC/USD:BTC"] = _swap("BTC/USD:BTC", quote="USD")
    markets["ETH/USDT"] = {
        "symbol": "ETH/USDT",
        "base": "ETH",
        "quote": "USDT",
        "spot": True,
        "swap": False,
        "linear": False,
        "active": True,
    }

    class FakeExchange:
        def load_markets(self):
            return markets

    monkeypatch.setattr(market, "exchange", lambda: FakeExchange())

    discovered = market.symbols()

    assert discovered[:5] == preferred
    assert len(discovered) == 305
    assert discovered[-1] == "ASSET299/USDT:USDT"
    assert "INACTIVE/USDT:USDT" not in discovered
    assert "INVERSE/USDT:USDT" not in discovered
    assert "BTC/USD:BTC" not in discovered
    assert "ETH/USDT" not in discovered
    assert len(discovered) > 250  # regression: never restore the old hidden cap


def test_market_catalog_requests_tickers_for_every_eligible_symbol(monkeypatch):
    markets = {
        f"ASSET{i:03d}/USDT:USDT": _swap(f"ASSET{i:03d}/USDT:USDT")
        for i in range(275)
    }

    class FakeExchange:
        has = {"fetchTickers": True}

        def __init__(self):
            self.requested = []

        def load_markets(self):
            return markets

        def fetch_tickers(self, symbols):
            self.requested = list(symbols)
            now = 1_800_000_000_000
            return {
                symbol: {
                    "last": 100.0 + i,
                    "percentage": 1.0,
                    "quoteVolume": 1_000_000.0 + i,
                    "baseVolume": 10_000.0 + i,
                    "bid": 99.0 + i,
                    "ask": 101.0 + i,
                    "high": 110.0 + i,
                    "low": 90.0 + i,
                    "timestamp": now,
                    "info": {},
                }
                for i, symbol in enumerate(symbols)
            }

    fake = FakeExchange()
    monkeypatch.setattr(market, "exchange", lambda: fake)

    catalog = market.market_catalog()

    assert len(fake.requested) == 275
    assert len(catalog) == 275
    assert {row["symbol"] for row in catalog} == set(markets)

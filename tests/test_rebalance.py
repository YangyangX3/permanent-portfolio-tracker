import asyncio

from app.portfolio import Portfolio, PortfolioAsset
from app.quotes import Quote, QuoteProvider
from app.rebalance import compute_portfolio_view


class _StubQuotes(QuoteProvider):
    def __init__(self, mapping: dict[str, Quote]):
        self._mapping = mapping

    async def get_quote(self, code: str) -> Quote:  # type: ignore[override]
        return self._mapping.get(code, Quote(code=code, name="", price=None, change_pct=None, as_of=None, source="stub"))

    async def get_quotes_bulk(self, codes: list[str]) -> dict[str, Quote]:  # type: ignore[override]
        return {c: self._mapping[c] for c in codes}

    async def get_coingecko_markets_bulk(self, ids: list[str]):  # type: ignore[override]
        return {}


class _StubChain:
    async def get_evm_token_balance(self, *, chain: str, wallet: str, token_address: str | None):
        raise AssertionError("chain should not be called in this test")


def test_rebalance_warns_when_out_of_band() -> None:
    cats = Portfolio.default().categories
    portfolio = Portfolio(
        categories=cats,
        assets=[
            PortfolioAsset(kind="cn", code="AAA", name="A", quantity=2, category_id="equity"),  # 40%
            PortfolioAsset(kind="cn", code="BBB", name="B", quantity=1, category_id="cash"),
            PortfolioAsset(kind="cn", code="CCC", name="C", quantity=1, category_id="gold"),
            PortfolioAsset(kind="cn", code="DDD", name="D", quantity=1, category_id="bond"),
        ],
    )
    quotes = _StubQuotes(
        {
            "AAA": Quote(code="AAA", name="A", price=100, change_pct=0.0, as_of="t", source="stub"),
            "BBB": Quote(code="BBB", name="B", price=100, change_pct=0.0, as_of="t", source="stub"),
            "CCC": Quote(code="CCC", name="C", price=100, change_pct=0.0, as_of="t", source="stub"),
            "DDD": Quote(code="DDD", name="D", price=100, change_pct=0.0, as_of="t", source="stub"),
        }
    )
    view = asyncio.run(compute_portfolio_view(portfolio=portfolio, quotes=quotes, chain=_StubChain()))
    assert view.total_value == 500
    assert len(view.rebalance_warnings) == 1
    assert len(view.warnings) == 1

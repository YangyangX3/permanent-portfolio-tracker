import asyncio

from app.rebalance_suggest import compute_contribution_suggestion


def test_contribution_suggestion_sums() -> None:
    from app.portfolio import Portfolio, PortfolioAsset
    from app.quotes import Quote, QuoteProvider
    from app.rebalance import compute_portfolio_view

    class _StubQuotes(QuoteProvider):
        def __init__(self, mapping):
            self._mapping = mapping

        async def get_quote(self, code: str) -> Quote:  # type: ignore[override]
            return self._mapping[code]

        async def get_coingecko_market(self, coingecko_id: str) -> Quote:  # type: ignore[override]
            raise AssertionError("not used")

        async def get_quotes_bulk(self, codes: list[str]) -> dict[str, Quote]:  # type: ignore[override]
            return {c: self._mapping[c] for c in codes}

        async def get_coingecko_markets_bulk(self, ids: list[str]):  # type: ignore[override]
            return {}

    class _StubChain:
        async def get_evm_token_balance(self, *, chain: str, wallet: str, token_address: str | None):
            raise AssertionError("not used")

    p = Portfolio(
        categories=Portfolio.default().categories,
        assets=[
            PortfolioAsset(kind="cn", code="A", name="A", quantity=1, category_id="equity"),
            PortfolioAsset(kind="cn", code="B", name="B", quantity=1, category_id="cash"),
            PortfolioAsset(kind="cn", code="C", name="C", quantity=1, category_id="gold"),
            PortfolioAsset(kind="cn", code="D", name="D", quantity=1, category_id="bond"),
        ],
    )
    q = _StubQuotes(
        {
            "A": Quote(code="A", name="A", price=100, change_pct=0.0, as_of="t", source="stub"),
            "B": Quote(code="B", name="B", price=100, change_pct=0.0, as_of="t", source="stub"),
            "C": Quote(code="C", name="C", price=100, change_pct=0.0, as_of="t", source="stub"),
            "D": Quote(code="D", name="D", price=100, change_pct=0.0, as_of="t", source="stub"),
        }
    )
    view = asyncio.run(compute_portfolio_view(portfolio=p, quotes=q, chain=_StubChain()))
    s = compute_contribution_suggestion(view=view, contribution_amount_cny=1000)
    assert round(sum(c.allocate_amount for c in s.categories), 2) == 1000.00


def test_contribution_suggestion_respects_bucket_weights() -> None:
    from app.portfolio import Portfolio, PortfolioAsset
    from app.quotes import Quote, QuoteProvider
    from app.rebalance import compute_portfolio_view

    class _StubQuotes(QuoteProvider):
        def __init__(self, mapping):
            self._mapping = mapping

        async def get_quote(self, code: str) -> Quote:  # type: ignore[override]
            return self._mapping[code]

        async def get_coingecko_market(self, coingecko_id: str) -> Quote:  # type: ignore[override]
            raise AssertionError("not used")

        async def get_quotes_bulk(self, codes: list[str]) -> dict[str, Quote]:  # type: ignore[override]
            return {c: self._mapping[c] for c in codes}

        async def get_coingecko_markets_bulk(self, ids: list[str]):  # type: ignore[override]
            return {}

    class _StubChain:
        async def get_evm_token_balance(self, *, chain: str, wallet: str, token_address: str | None):
            raise AssertionError("not used")

    p = Portfolio(
        categories=Portfolio.default().categories,
        assets=[
            PortfolioAsset(kind="cn", code="E1", name="E1", quantity=1, category_id="equity", bucket_weight=0.75),
            PortfolioAsset(kind="cn", code="E2", name="E2", quantity=1, category_id="equity", bucket_weight=0.25),
            PortfolioAsset(kind="cn", code="C", name="C", quantity=1, category_id="cash"),
            PortfolioAsset(kind="cn", code="G", name="G", quantity=1, category_id="gold"),
            PortfolioAsset(kind="cn", code="B", name="B", quantity=1, category_id="bond"),
        ],
    )
    q = _StubQuotes(
        {
            "E1": Quote(code="E1", name="E1", price=50, change_pct=0.0, as_of="t", source="stub"),
            "E2": Quote(code="E2", name="E2", price=50, change_pct=0.0, as_of="t", source="stub"),
            "C": Quote(code="C", name="C", price=100, change_pct=0.0, as_of="t", source="stub"),
            "G": Quote(code="G", name="G", price=100, change_pct=0.0, as_of="t", source="stub"),
            "B": Quote(code="B", name="B", price=100, change_pct=0.0, as_of="t", source="stub"),
        }
    )
    view = asyncio.run(compute_portfolio_view(portfolio=p, quotes=q, chain=_StubChain()))
    # total_before: equity=100, others=100 => 400. contribute 400 => each bucket delta=100.
    s = compute_contribution_suggestion(view=view, contribution_amount_cny=400)
    equity = next(c for c in s.categories if c.category_id == "equity")
    assert round(equity.allocate_amount, 2) == 100.00
    # split inside equity bucket by 75/25
    by_name = {a.name: a.amount_cny for a in equity.assets}
    assert round(by_name["E1"], 2) == 75.00
    assert round(by_name["E2"], 2) == 25.00


def test_full_balance_cash_needed() -> None:
    import asyncio

    from app.portfolio import Portfolio, PortfolioAsset
    from app.quotes import Quote, QuoteProvider
    from app.rebalance import compute_portfolio_view
    from app.rebalance_suggest import compute_full_balance_cash_needed

    class _StubQuotes(QuoteProvider):
        def __init__(self, mapping):
            self._mapping = mapping

        async def get_quotes_bulk(self, codes: list[str]) -> dict[str, Quote]:  # type: ignore[override]
            return {c: self._mapping[c] for c in codes}

        async def get_coingecko_markets_bulk(self, ids: list[str]):  # type: ignore[override]
            return {}

    class _StubChain:
        async def get_evm_token_balance(self, *, chain: str, wallet: str, token_address: str | None):
            raise AssertionError("not used")

    # equity overweight: 400 vs total 1000 -> need X so that 400 becomes 25% => 1000+X = 1600 => X=600
    p = Portfolio(
        categories=Portfolio.default().categories,
        assets=[
            PortfolioAsset(kind="cn", code="A", name="A", quantity=4, category_id="equity"),  # 400
            PortfolioAsset(kind="cn", code="B", name="B", quantity=2, category_id="cash"),  # 200
            PortfolioAsset(kind="cn", code="C", name="C", quantity=2, category_id="gold"),  # 200
            PortfolioAsset(kind="cn", code="D", name="D", quantity=2, category_id="bond"),  # 200
        ],
    )
    q = _StubQuotes({k: Quote(code=k, name=k, price=100, change_pct=0.0, as_of="t", source="stub") for k in ["A", "B", "C", "D"]})
    view = asyncio.run(compute_portfolio_view(portfolio=p, quotes=q, chain=_StubChain()))
    assert round(compute_full_balance_cash_needed(view=view), 6) == 600.0

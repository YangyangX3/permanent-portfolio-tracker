from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.chain import ChainProvider
from app.portfolio import Category, Portfolio, PortfolioAsset
from app.quotes import QuoteProvider


@dataclass(frozen=True)
class AssetView:
    id: str
    kind: str
    category_id: str | None
    bucket_weight: float | None
    code: str
    name: str
    quantity: float | None
    price: float | None
    change_pct: float | None
    as_of: str | None
    source: str
    value: float
    status: str  # ok | warn | error
    note: str


@dataclass(frozen=True)
class CategoryView:
    id: str
    name: str
    value: float
    weight: float
    target_weight: float
    min_weight: float
    max_weight: float
    status: str  # ok | warn
    note: str
    assets: list[AssetView]


@dataclass(frozen=True)
class PortfolioView:
    total_value: float
    as_of: str | None
    categories: list[CategoryView]
    unassigned: list[AssetView]
    rebalance_warnings: list[str]
    warnings: list[str]


async def compute_portfolio_view(*, portfolio: Portfolio, quotes: QuoteProvider, chain: ChainProvider) -> PortfolioView:
    asset_views, as_of = await _compute_assets(portfolio=portfolio, quotes=quotes, chain=chain)
    total_value = sum(a.value for a in asset_views)

    categories_by_id: dict[str, Category] = {c.id: c for c in portfolio.categories}
    grouped: dict[str, list[AssetView]] = {c.id: [] for c in portfolio.categories}
    unassigned: list[AssetView] = []
    for a in asset_views:
        if a.category_id and a.category_id in grouped:
            grouped[a.category_id].append(a)
        else:
            unassigned.append(a)

    categories: list[CategoryView] = []
    rebalance_warnings: list[str] = []
    warnings: list[str] = []
    for c in portfolio.categories:
        assets = grouped.get(c.id, [])
        value = sum(a.value for a in assets)
        weight = (value / total_value) if total_value > 0 else 0.0
        status = "ok"
        note = ""
        if total_value > 0 and (weight < c.min_weight or weight > c.max_weight):
            status = "warn"
            note = "超出阈值，建议再平衡"
            rebalance_warnings.append(f"{c.name} 当前占比 {weight:.1%} 超出 [{c.min_weight:.0%}, {c.max_weight:.0%}]")
        categories.append(
            CategoryView(
                id=c.id,
                name=c.name,
                value=value,
                weight=weight,
                target_weight=c.target_weight,
                min_weight=c.min_weight,
                max_weight=c.max_weight,
                status=status,
                note=note,
                assets=assets,
            )
        )

    if unassigned:
        warnings.append(f"有 {len(unassigned)} 个资产未分配到四类资产桶（请在资产设置页拖动分配）")
    for a in asset_views:
        if a.status == "error":
            warnings.append(f"{a.name} 数据获取失败（{a.note or a.source}）")

    warnings = rebalance_warnings + warnings
    return PortfolioView(
        total_value=total_value,
        as_of=as_of,
        categories=categories,
        unassigned=unassigned,
        rebalance_warnings=rebalance_warnings,
        warnings=warnings,
    )


async def _compute_assets(*, portfolio: Portfolio, quotes: QuoteProvider, chain: ChainProvider) -> tuple[list[AssetView], str | None]:
    cn_assets = [a for a in portfolio.assets if a.kind == "cn" and a.code]
    crypto_assets = [a for a in portfolio.assets if a.kind == "crypto" and a.coingecko_id]

    cn_codes = [a.code for a in cn_assets]
    cg_ids = [a.coingecko_id or "" for a in crypto_assets]

    crypto_balance_assets = [a for a in crypto_assets if getattr(a, "manual_quantity", None) is None]
    if crypto_balance_assets:
        balances_task = asyncio.gather(
            *[
                chain.get_evm_token_balance(chain=a.chain or "", wallet=a.wallet or "", token_address=a.token_address)
                for a in crypto_balance_assets
            ],
            return_exceptions=True,
        )
    else:
        balances_task = asyncio.sleep(0, result=[])

    cn_task = quotes.get_quotes_bulk(cn_codes)
    cg_task = quotes.get_coingecko_markets_bulk(cg_ids)

    cn_quotes, cg_markets, balances = await asyncio.gather(cn_task, cg_task, balances_task)
    cn_map = cn_quotes
    cg_map = cg_markets

    balances_by_asset_id: dict[str, object] = {}
    for a, b in zip(crypto_balance_assets, balances, strict=False):
        balances_by_asset_id[a.id] = b

    out: list[AssetView] = []
    as_of = None
    for asset in portfolio.assets:
        try:
            if asset.kind == "cash":
                v = _compute_cash(asset=asset)
            elif asset.kind == "cn":
                q = cn_map.get(asset.code) if asset.code else None
                if q is None:
                    v = AssetView(
                        id=asset.id,
                        kind="cn",
                        category_id=asset.category_id,
                        bucket_weight=asset.bucket_weight,
                        code=asset.code,
                        name=(asset.name or asset.code or asset.id).strip(),
                        quantity=max(0.0, asset.quantity),
                        price=None,
                        change_pct=None,
                        as_of=None,
                        source="unavailable",
                        value=0.0,
                        status="error",
                        note="行情获取失败",
                    )
                else:
                    name = (q.name or asset.name or asset.code).strip() or asset.id
                    qty = max(0.0, asset.quantity)
                    price = q.price
                    value = (qty * price) if price is not None else 0.0
                    status = "ok" if price is not None else "error"
                    note = "" if status == "ok" else "行情获取失败"
                    v = AssetView(
                        id=asset.id,
                        kind="cn",
                        category_id=asset.category_id,
                        bucket_weight=asset.bucket_weight,
                        code=asset.code,
                        name=name,
                        quantity=qty,
                        price=price,
                        change_pct=q.change_pct,
                        as_of=q.as_of,
                        source=q.source,
                        value=value,
                        status=status,
                        note=note,
                    )
            elif asset.kind == "crypto":
                bal_obj = balances_by_asset_id.get(asset.id)
                bal = None
                bal_err = None
                if isinstance(bal_obj, Exception):
                    bal_err = str(bal_obj)
                else:
                    bal = bal_obj
                market = cg_map.get((asset.coingecko_id or "").strip().lower())
                price = market.price if market else None
                change_pct = market.change_pct if market else None
                mname = market.name if market else ""

                manual_qty = getattr(asset, "manual_quantity", None)
                if manual_qty is not None:
                    qty = manual_qty
                    sym = None
                    bal_source = "manual-quantity"
                    bal_error = None
                else:
                    qty = getattr(bal, "quantity", None) if bal is not None else None
                    sym = getattr(bal, "symbol", None) if bal is not None else None
                    bal_source = getattr(bal, "source", "chain") if bal is not None else "chain"
                    bal_error = getattr(bal, "error", None) if bal is not None else None
                if bal_err and not bal_error:
                    bal_error = bal_err

                name = (asset.name or mname or sym or asset.coingecko_id or "crypto").strip()
                value = (qty * price) if (qty is not None and price is not None) else 0.0
                status = "ok"
                note_parts: list[str] = []
                if bal_error:
                    status = "error"
                    note_parts.append(str(bal_error))
                if price is None:
                    status = "error"
                    note_parts.append("missing price (coingecko)")
                note = "；".join([p for p in note_parts if p])
                display_code = (asset.coingecko_id or asset.token_address or "crypto").strip()
                v = AssetView(
                    id=asset.id,
                    kind="crypto",
                    category_id=asset.category_id,
                    bucket_weight=asset.bucket_weight,
                    code=display_code,
                    name=name,
                    quantity=qty,
                    price=price,
                    change_pct=change_pct,
                    as_of=None,
                    source=f"{bal_source}+{(market.source if market else 'coingecko')}",
                    value=value,
                    status=status,
                    note=note,
                )
            else:
                v = AssetView(
                    id=asset.id,
                    kind=str(asset.kind),
                    category_id=asset.category_id,
                    bucket_weight=asset.bucket_weight,
                    code=asset.code or asset.id,
                    name=(asset.name or asset.code or asset.id).strip(),
                    quantity=None,
                    price=None,
                    change_pct=None,
                    as_of=None,
                    source="unavailable",
                    value=0.0,
                    status="error",
                    note="unsupported asset kind",
                )
        except Exception as e:
            v = AssetView(
                id=asset.id,
                kind=asset.kind,
                category_id=asset.category_id,
                bucket_weight=asset.bucket_weight,
                code=asset.code or asset.id,
                name=asset.name or asset.code or asset.id,
                quantity=None,
                price=None,
                change_pct=None,
                as_of=None,
                source="error",
                value=0.0,
                status="error",
                note=f"{type(e).__name__}: {e}",
            )
        out.append(v)
        if as_of is None and v.as_of:
            as_of = v.as_of

    return out, as_of


async def _compute_one(*, asset: PortfolioAsset, quotes: QuoteProvider, chain: ChainProvider) -> AssetView:
    if asset.kind == "crypto":
        return await _compute_crypto(asset=asset, quotes=quotes, chain=chain)
    if asset.kind == "cash":
        return _compute_cash(asset=asset)
    return await _compute_cn(asset=asset, quotes=quotes)


async def _compute_cn(*, asset: PortfolioAsset, quotes: QuoteProvider) -> AssetView:
    q = await quotes.get_quote(asset.code)
    name = (q.name or asset.name or asset.code).strip() or asset.id
    qty = max(0.0, asset.quantity)
    price = q.price
    value = (qty * price) if price is not None else 0.0
    status = "ok" if price is not None else "error"
    note = "" if status == "ok" else "行情获取失败"
    return AssetView(
        id=asset.id,
        kind="cn",
        category_id=asset.category_id,
        bucket_weight=asset.bucket_weight,
        code=asset.code,
        name=name,
        quantity=qty,
        price=price,
        change_pct=q.change_pct,
        as_of=q.as_of,
        source=q.source,
        value=value,
        status=status,
        note=note,
    )


async def _compute_crypto(*, asset: PortfolioAsset, quotes: QuoteProvider, chain: ChainProvider) -> AssetView:
    manual_qty = getattr(asset, "manual_quantity", None)
    if manual_qty is not None:
        bal_qty = manual_qty
        bal_symbol = None
        bal_source = "manual-quantity"
        bal_error = None
    else:
        bal = await chain.get_evm_token_balance(chain=asset.chain or "", wallet=asset.wallet or "", token_address=asset.token_address)
        bal_qty = bal.quantity
        bal_symbol = bal.symbol
        bal_source = bal.source
        bal_error = bal.error
    market = await quotes.get_coingecko_market(asset.coingecko_id or "")
    name = (asset.name or market.name or bal_symbol or asset.coingecko_id or "crypto").strip()

    qty = bal_qty
    price = market.price
    value = (qty * price) if (qty is not None and price is not None) else 0.0

    status = "ok"
    note_parts: list[str] = []
    if bal_error:
        status = "error"
        note_parts.append(bal_error)
    if price is None:
        status = "error"
        note_parts.append("missing price (coingecko)")
    note = "；".join([p for p in note_parts if p])

    display_code = (asset.coingecko_id or asset.token_address or "crypto").strip()
    return AssetView(
        id=asset.id,
        kind="crypto",
        category_id=asset.category_id,
        bucket_weight=asset.bucket_weight,
        code=display_code,
        name=name,
        quantity=qty,
        price=price,
        change_pct=market.change_pct,
        as_of=None,
        source=f"{bal_source}+{market.source}",
        value=value,
        status=status,
        note=note,
    )


def _compute_cash(*, asset: PortfolioAsset) -> AssetView:
    amount = float(asset.cash_amount_cny or 0.0)
    name = (asset.name or "现金").strip()
    return AssetView(
        id=asset.id,
        kind="cash",
        category_id=asset.category_id or "cash",
        bucket_weight=asset.bucket_weight,
        code="CASH",
        name=name,
        quantity=amount,
        price=1.0,
        change_pct=0.0,
        as_of=None,
        source="manual-cash",
        value=amount,
        status="ok",
        note="",
    )

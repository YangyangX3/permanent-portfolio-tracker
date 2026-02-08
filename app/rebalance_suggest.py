from __future__ import annotations

from dataclasses import dataclass

from app.rebalance import PortfolioView


@dataclass(frozen=True)
class AssetBuySuggestion:
    asset_id: str | None
    name: str
    code: str
    amount_cny: float
    est_quantity: float | None
    note: str


@dataclass(frozen=True)
class CategorySuggestion:
    category_id: str
    name: str
    current_value: float
    current_weight: float
    target_weight: float
    target_value_after: float
    allocate_amount: float
    weight_after: float
    assets: list[AssetBuySuggestion]


@dataclass(frozen=True)
class ContributionSuggestion:
    contribution_amount: float
    total_before: float
    total_after: float
    categories: list[CategorySuggestion]
    note: str


def compute_contribution_suggestion(
    *,
    view: PortfolioView,
    contribution_amount_cny: float,
    prefill_assets: dict[str, float] | None = None,
    prefill_in_view: bool = False,
) -> ContributionSuggestion:
    contribution_amount_cny = max(0.0, float(contribution_amount_cny))
    prefill_assets = prefill_assets or {}
    prefill_by_category: dict[str, float] = {}
    prefill_total = 0.0
    exclude_asset_ids: set[str] = set()

    asset_category: dict[str, str] = {}
    for c in view.categories:
        for a in c.assets:
            asset_category[str(a.id)] = c.id

    for aid, raw_amt in prefill_assets.items():
        try:
            amt = float(raw_amt)
        except Exception:
            continue
        if amt <= 0:
            continue
        key = str(aid)
        exclude_asset_ids.add(key)
        cid = asset_category.get(key)
        if not prefill_in_view:
            prefill_total += amt
            if cid:
                prefill_by_category[cid] = prefill_by_category.get(cid, 0.0) + amt

    total_before = max(0.0, float(view.total_value)) + prefill_total
    total_after = total_before + contribution_amount_cny

    # If total is zero, just split by target weights
    if total_after <= 0:
        cats = []
        for c in view.categories:
            cats.append(
                CategorySuggestion(
                    category_id=c.id,
                    name=c.name,
                    current_value=0.0,
                    current_weight=0.0,
                    target_weight=c.target_weight,
                    target_value_after=0.0,
                    allocate_amount=0.0,
                    weight_after=0.0,
                    assets=[],
                )
            )
        return ContributionSuggestion(
            contribution_amount=contribution_amount_cny,
            total_before=total_before,
            total_after=total_after,
            categories=cats,
            note="组合总市值为 0，建议先录入持仓或现金金额。",
        )

    current_values = {c.id: c.value + prefill_by_category.get(c.id, 0.0) for c in view.categories}
    target_value_after = {c.id: total_after * c.target_weight for c in view.categories}
    deltas = {c.id: max(0.0, target_value_after[c.id] - current_values.get(c.id, 0.0)) for c in view.categories}
    remaining = contribution_amount_cny
    alloc = {c.id: 0.0 for c in view.categories}

    # Iteratively fill underweight categories up to their delta.
    while remaining > 1e-6:
        positives = [(cid, d) for cid, d in deltas.items() if d > 1e-6]
        if not positives:
            break
        total_need = sum(d for _, d in positives)
        if total_need <= 1e-6:
            break
        for cid, d in positives:
            share = remaining * (d / total_need)
            take = min(d, share)
            alloc[cid] += take
            deltas[cid] -= take
        new_remaining = contribution_amount_cny - sum(alloc.values())
        if abs(new_remaining - remaining) < 1e-6:
            break
        remaining = new_remaining

    # If still remaining (e.g. already above target), put into lowest-weight categories.
    if remaining > 1e-6:
        ordered = sorted(view.categories, key=lambda c: c.weight)
        per = remaining / max(1, len(ordered))
        for c in ordered:
            alloc[c.id] += per
        remaining = 0.0

    cats: list[CategorySuggestion] = []
    categories_map = {c.id: c for c in view.categories}
    for c in view.categories:
        current_val = current_values.get(c.id, 0.0)
        new_val = current_val + alloc[c.id]
        per_assets: list[AssetBuySuggestion] = []
        if alloc[c.id] > 0:
            cat_view = categories_map.get(c.id)
            buyables = []
            if cat_view:
                for a in cat_view.assets:
                    if a.id in exclude_asset_ids:
                        continue
                    if a.kind in {"cn", "crypto", "cash"}:
                        buyables.append(a)
            if not buyables:
                if c.id == "cash":
                    per_assets.append(
                        AssetBuySuggestion(
                            asset_id=None,
                            name="现金",
                            code="CASH",
                            amount_cny=alloc[c.id],
                            est_quantity=None,
                            note="留作现金",
                        )
                    )
                else:
                    per_assets.append(
                        AssetBuySuggestion(
                            asset_id=None,
                            name="（无可买资产）",
                            code=c.id,
                            amount_cny=alloc[c.id],
                            est_quantity=None,
                            note="请先在该桶内添加可买标的",
                        )
                    )
            else:
                weights = _bucket_asset_weights(buyables)
                for a in buyables:
                    per = alloc[c.id] * weights.get(a.id, 0.0)
                    if per <= 0:
                        continue
                    est_qty = None
                    note = "按桶内占比分配；未考虑最小交易单位/手续费"
                    if a.kind != "cash" and a.price and a.price > 0:
                        est_qty = per / a.price
                    elif a.kind != "cash":
                        note = "按桶内占比分配；当前缺少价格，无法估算份额"
                    per_assets.append(
                        AssetBuySuggestion(
                            asset_id=a.id,
                            name=a.name,
                            code=a.code,
                            amount_cny=per,
                            est_quantity=est_qty,
                            note=note,
                        )
                    )
        cats.append(
            CategorySuggestion(
                category_id=c.id,
                name=c.name,
                current_value=current_val,
                current_weight=(current_val / total_before) if total_before > 0 else 0.0,
                target_weight=c.target_weight,
                target_value_after=target_value_after.get(c.id, new_val),
                allocate_amount=alloc[c.id],
                weight_after=(new_val / total_after) if total_after > 0 else 0.0,
                assets=per_assets,
            )
        )

    note = "优先补齐低于目标权重的资产桶；若仍有剩余，按当前权重从低到高均分。"
    return ContributionSuggestion(
        contribution_amount=contribution_amount_cny,
        total_before=total_before,
        total_after=total_after,
        categories=cats,
        note=note,
    )

def compute_full_balance_cash_needed(*, view: PortfolioView) -> float:
    """
    计算“完全平衡到目标权重”所需的最小新增资金（只加钱不卖出）。

    设每个桶当前市值为 v_i，总市值为 T，目标权重为 p_i。
    为了在不卖出的前提下让所有桶达到目标（即目标市值 >= 当前市值），需要：
        T + X >= v_i / p_i  ->  X >= v_i / p_i - T
    因此最小新增资金为 max_i(v_i / p_i - T, 0)。
    """
    bucket_total = float(sum(c.value for c in view.categories))
    if bucket_total <= 0:
        return 0.0
    need = 0.0
    for c in view.categories:
        p = float(getattr(c, "target_weight", 0.0) or 0.0)
        if p <= 0:
            continue
        need = max(need, float(c.value) / p - bucket_total)
    return max(0.0, need)


def _bucket_asset_weights(assets) -> dict[str, float]:
    n = len(assets)
    if n <= 0:
        return {}

    specified = {a.id: float(a.bucket_weight) for a in assets if a.bucket_weight is not None}
    unspecified = [a for a in assets if a.bucket_weight is None]

    if not specified:
        return {a.id: 1.0 / n for a in assets}

    specified_sum = sum(max(0.0, w) for w in specified.values())
    if specified_sum <= 1e-9:
        return {a.id: 1.0 / n for a in assets}

    # If specified sum > 1, normalize all specified weights and set unspecified to 0.
    if specified_sum > 1.0 + 1e-6:
        return {aid: max(0.0, w) / specified_sum for aid, w in specified.items()}

    remaining = max(0.0, 1.0 - specified_sum)
    per_unspec = (remaining / len(unspecified)) if unspecified else 0.0

    out: dict[str, float] = {}
    for a in assets:
        if a.id in specified:
            out[a.id] = max(0.0, specified[a.id])
        else:
            out[a.id] = per_unspec

    total = sum(out.values())
    if total <= 1e-9:
        return {a.id: 1.0 / n for a in assets}
    return {aid: w / total for aid, w in out.items()}

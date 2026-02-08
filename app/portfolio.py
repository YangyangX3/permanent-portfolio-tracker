from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PORTFOLIO_PATH = DATA_DIR / "portfolio.json"


class Category(BaseModel):
    id: str
    name: str
    target_weight: float = Field(0.25, ge=0, le=1)
    min_weight: float = Field(0.15, ge=0, le=1)
    max_weight: float = Field(0.35, ge=0, le=1)


class PortfolioAsset(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    kind: Literal["cn", "crypto", "cash"] = "cn"

    # cn
    code: str = Field("", description="股票/ETF/基金代码，如 510300 / 600519 / 161725")
    name: str = Field("", description="自定义名称（可空，行情接口返回时会补全）")
    quantity: float = Field(0.0, ge=0, description="cn 持仓数量（份/股）")

    # bucket assignment (4-category permanent portfolio)
    category_id: str | None = None
    bucket_weight: float | None = Field(None, ge=0, le=1, description="桶内资产占比（可空=自动均分或按剩余权重分配）")

    # crypto (EVM)
    chain: str | None = Field(None, description="例如 eth / bsc / polygon")
    wallet: str | None = Field(None, description="0x 开头的钱包地址")
    token_address: str | None = Field(None, description="ERC20 合约地址；为空表示原生币")
    coingecko_id: str | None = Field(None, description="CoinGecko 币种 id，用于价格与24h涨跌幅")
    manual_quantity: float | None = Field(None, ge=0, description="crypto 手动数量（可空；非空时不读链上余额）")

    # cash (manual)
    cash_amount_cny: float | None = Field(None, ge=0, description="现金金额（CNY）")


class Portfolio(BaseModel):
    base_currency: str = "CNY"
    categories: list[Category] = Field(default_factory=list)
    assets: list[PortfolioAsset] = Field(default_factory=list)

    @staticmethod
    def default() -> "Portfolio":
        categories = [
            Category(id="equity", name="权益（ETF/股票）", target_weight=0.25, min_weight=0.15, max_weight=0.35),
            Category(id="cash", name="现金（货基/货币ETF）", target_weight=0.25, min_weight=0.15, max_weight=0.35),
            Category(id="gold", name="黄金（ETF/基金）", target_weight=0.25, min_weight=0.15, max_weight=0.35),
            Category(id="bond", name="长期债券（ETF/基金）", target_weight=0.25, min_weight=0.15, max_weight=0.35),
        ]
        return Portfolio(
            categories=categories,
            assets=[
                PortfolioAsset(code="510300", name="沪深300ETF", quantity=0, category_id="equity"),
                PortfolioAsset(code="511880", name="货币ETF/现金替代", quantity=0, category_id="cash"),
                PortfolioAsset(code="518880", name="黄金ETF", quantity=0, category_id="gold"),
                PortfolioAsset(code="511010", name="国债/债券ETF示例", quantity=0, category_id="bond"),
            ]
        )


def normalize_portfolio(portfolio: Portfolio) -> Portfolio:
    # Ensure 4 categories exist
    if not portfolio.categories:
        portfolio.categories = Portfolio.default().categories

    cat_ids = {c.id for c in portfolio.categories}

    for asset in portfolio.assets:
        if not getattr(asset, "id", None):
            asset.id = uuid.uuid4().hex
        if not getattr(asset, "kind", None):
            asset.kind = "crypto" if (asset.wallet or asset.chain or asset.token_address) else "cn"
        if asset.category_id not in cat_ids:
            asset.category_id = None
        if asset.kind == "cn" and not asset.code:
            asset.code = ""
        if asset.kind == "crypto":
            asset.quantity = 0.0
            if asset.manual_quantity is not None:
                try:
                    mq = float(asset.manual_quantity)
                    asset.manual_quantity = mq if mq >= 0 else None
                except Exception:
                    asset.manual_quantity = None
        if asset.kind == "cash":
            asset.code = ""
            asset.quantity = 0.0
            if asset.cash_amount_cny is None:
                asset.cash_amount_cny = 0.0
        if getattr(asset, "bucket_weight", None) is not None:
            try:
                bw = float(asset.bucket_weight)  # type: ignore[arg-type]
                asset.bucket_weight = bw if bw >= 0 else None
            except Exception:
                asset.bucket_weight = None
    return portfolio


def _coerce_bucket_weight(value) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
    except Exception:
        return None

    # Allow "20" meaning 20%.
    if v > 1.0 and v <= 100.0:
        v = v / 100.0
    if v < 0 or v > 1:
        return None
    return v


def _sanitize_portfolio_dict(data: object) -> dict:
    if not isinstance(data, dict):
        return {}

    out = dict(data)

    assets = out.get("assets")
    if isinstance(assets, list):
        new_assets = []
        for a in assets:
            if not isinstance(a, dict):
                continue
            aa = dict(a)
            if "bucket_weight" in aa:
                aa["bucket_weight"] = _coerce_bucket_weight(aa.get("bucket_weight"))
            for key in ("quantity", "cash_amount_cny", "manual_quantity"):
                if key in aa:
                    try:
                        v = float(aa.get(key) or 0.0)
                        aa[key] = v if v >= 0 else 0.0
                    except Exception:
                        aa[key] = 0.0
            new_assets.append(aa)
        out["assets"] = new_assets

    cats = out.get("categories")
    if isinstance(cats, list):
        new_cats = []
        for c in cats:
            if not isinstance(c, dict):
                continue
            cc = dict(c)
            for key in ("target_weight", "min_weight", "max_weight"):
                if key not in cc:
                    continue
                try:
                    v = float(cc.get(key) or 0.0)
                    if v > 1.0 and v <= 100.0:
                        v = v / 100.0
                    if v < 0:
                        v = 0.0
                    if v > 1:
                        v = 1.0
                    cc[key] = v
                except Exception:
                    pass
            new_cats.append(cc)
        out["categories"] = new_cats

    return out


def load_portfolio() -> Portfolio:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PORTFOLIO_PATH.exists():
        portfolio = Portfolio.default()
        save_portfolio(portfolio)
        return portfolio
    raw_text = PORTFOLIO_PATH.read_text(encoding="utf-8")
    original_data = json.loads(raw_text)
    data = original_data
    repaired_on_read = False
    try:
        portfolio = Portfolio.model_validate(data)
    except ValidationError:
        # Attempt to repair common user-input mistakes (e.g. bucket_weight "20" meaning 20%).
        repaired = _sanitize_portfolio_dict(data)
        portfolio = Portfolio.model_validate(repaired)
        data = repaired
        repaired_on_read = True
    portfolio = normalize_portfolio(portfolio)

    # Avoid rewriting portfolio.json on every read; only persist when repair/normalization changes something.
    try:
        normalized = portfolio.model_dump()
        if repaired_on_read or normalized != original_data:
            save_portfolio(portfolio)
    except Exception:
        # If comparison fails for any reason, fall back to saving the normalized version.
        save_portfolio(portfolio)
    return portfolio


def save_portfolio(portfolio: Portfolio) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_PATH.write_text(
        json.dumps(portfolio.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

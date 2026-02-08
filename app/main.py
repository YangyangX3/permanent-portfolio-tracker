from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.chain import ChainProvider
from app.ledger import (
    LedgerEntry,
    add_ledger_entry,
    add_ledger_entries,
    compute_metrics,
    delete_ledger_entry,
    load_ledger,
    parse_date_input,
)
from app.mailer import send_email
from app.notifications import load_notification_state, save_notification_state, should_send_threshold
from app.portfolio import (
    Portfolio,
    PortfolioAsset,
    PORTFOLIO_PATH,
    load_portfolio,
    save_portfolio,
)
from app.quotes import QuoteProvider
from app.rebalance import CategoryView, PortfolioView, compute_portfolio_view
from app.runtime_cache import PortfolioRuntimeCache
from app.scheduler import first_workday_of_month_cn, format_email_body
from app.scheduler import maybe_send_threshold_email_for_view, start_scheduler
from app.settings import Settings, SettingsOverride, effective_settings_dict, load_settings_override, save_settings_override
from app.snapshots import maybe_append_snapshot
from app.snapshots import SNAPSHOT_PATH
from app.total_history import build_total_history_payload, load_total_history_points, parse_window_seconds

app = FastAPI(title="Permanent Portfolio Tracker")

quotes = QuoteProvider()
chain = ChainProvider()
settings = Settings.load()
_scheduler = None
_cache_task: asyncio.Task | None = None
runtime_cache = PortfolioRuntimeCache()

def _env_float(name: str, default: float) -> float:
    try:
        v = os.environ.get(name)
        if v is None:
            return default
        s = v.strip()
        return float(s) if s else default
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        v = os.environ.get(name)
        if v is None:
            return default
        s = v.strip()
        return int(s) if s else default
    except Exception:
        return default


_CACHE_ACTIVE_REFRESH_INTERVAL_SECONDS = max(1.0, _env_float("PP_CACHE_ACTIVE_REFRESH_SECONDS", 4.0))
_CACHE_IDLE_REFRESH_INTERVAL_SECONDS = max(2.0, _env_float("PP_CACHE_IDLE_REFRESH_SECONDS", 20.0))
_CACHE_IDLE_AFTER_SECONDS = max(5.0, _env_float("PP_CACHE_IDLE_AFTER_SECONDS", 60.0))
_CACHE_SNAPSHOT_INTERVAL_SECONDS = max(10.0, _env_float("PP_SNAPSHOT_INTERVAL_SECONDS", 60.0))
_CACHE_MIN_REFRESH_GAP_SECONDS = max(0.25, _env_float("PP_CACHE_MIN_REFRESH_GAP_SECONDS", 1.0))

class ApiMoveRequest(BaseModel):
    category_id: str | None = None


class ApiAssetCreateRequest(BaseModel):
    kind: Literal["cn", "crypto", "cash"] = "cn"
    code: str | None = None
    name: str | None = None
    quantity: float | None = None

    chain: str | None = None
    wallet: str | None = None
    token_address: str | None = None
    coingecko_id: str | None = None
    manual_quantity: float | None = None

    cash_amount_cny: float | None = None

    category_id: str | None = None
    bucket_weight: float | None = None


class ApiAssetUpdateRequest(BaseModel):
    code: str | None = None
    name: str | None = None
    quantity: float | None = None

    chain: str | None = None
    wallet: str | None = None
    token_address: str | None = None
    coingecko_id: str | None = None
    manual_quantity: float | None = None

    cash_amount_cny: float | None = None

    category_id: str | None = None
    bucket_weight: float | None = None


class ApiAssetBatchUpdateItem(ApiAssetUpdateRequest):
    asset_id: str


class ApiLedgerCreateRequest(BaseModel):
    date: str | None = None  # YYYY-MM-DD
    direction: Literal["deposit", "withdraw"] = "deposit"
    amount_cny: float = 0.0
    asset_id: str | None = None
    note: str | None = None


class ApiAllocationApplyRequest(BaseModel):
    contribution: float = 0.0
    prefill_assets: dict[str, float] | None = None


class ApiSettingsUpdateRequest(BaseModel):
    timezone: str | None = None
    email_enabled: bool | None = None
    notify_cooldown_minutes: int | None = None
    daily_job_time: str | None = None
    crypto_slip_pct: float | None = None
    mail_from: str | None = None
    mail_to: list[str] | str | None = None

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_starttls: bool | None = None


def _parse_optional_float(raw: str) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = float(s)
        # For UX: allow users to input "20" meaning 20%.
        if v > 1.0 and v <= 100.0:
            v = v / 100.0
        if v < 0 or v > 1:
            return None
        return v
    except Exception:
        return None


def _parse_optional_nonneg_float(raw: str) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = float(s)
        return v if v >= 0 else None
    except Exception:
        return None


def _coerce_prefill_assets(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            amt = float(v)
        except Exception:
            continue
        if amt <= 0:
            continue
        out[str(k)] = amt
    return out


def _restart_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
    if settings.email_enabled:
        try:
            _scheduler = start_scheduler(settings=settings, quotes=quotes, chain=chain)
        except Exception:
            _scheduler = None


def _sanitize_settings_override_for_ui(override: SettingsOverride) -> dict:
    d = override.model_dump()
    d.pop("smtp_password_enc", None)
    d["smtp_password_set"] = bool(getattr(override, "smtp_password_enc", None))
    return d


@app.middleware("http")
async def _track_access_middleware(request: Request, call_next):
    # Used to reduce background refresh work when no one is using the UI.
    runtime_cache.last_access_at = datetime.now()
    return await call_next(request)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "cache_ready": runtime_cache.view is not None,
        "cache_updated_at": runtime_cache.updated_at.isoformat() if runtime_cache.updated_at else None,
        "cache_last_error": runtime_cache.last_error,
    }

@app.get("/api/ui/state")
async def api_ui_state() -> JSONResponse:
    portfolio = get_portfolio_cached()
    view = runtime_cache.view
    if view is None:
        # Do not block UI; background refresh will populate the cache soon.
        trigger_cache_refresh(force=True)

    payload = {
        "portfolio": portfolio.model_dump(),
        "view": asdict(view) if view is not None else None,
        "cache": {
            "updated_at": runtime_cache.updated_at.isoformat() if runtime_cache.updated_at else None,
            "last_duration_ms": runtime_cache.last_duration_ms,
            "last_error": runtime_cache.last_error,
        },
    }
    return JSONResponse(payload)


@app.get("/api/v2/state")
async def api_v2_state() -> JSONResponse:
    return await api_ui_state()


def _coerce_bucket_weight(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    # Allow "20" meaning 20%.
    if v > 1.0 and v <= 100.0:
        v = v / 100.0
    if v < 0 or v > 1:
        return None
    return v


@app.post("/api/v2/assets")
async def api_v2_assets_create(req: ApiAssetCreateRequest) -> JSONResponse:
    portfolio = load_portfolio()

    kind = (req.kind or "cn").strip().lower()
    bw = _coerce_bucket_weight(req.bucket_weight)
    cat = (req.category_id or "").strip() or None

    if kind == "cn":
        asset = PortfolioAsset(
            kind="cn",
            code=(req.code or "").strip(),
            name=(req.name or "").strip(),
            quantity=max(0.0, float(req.quantity or 0.0)),
            category_id=cat,
            bucket_weight=bw,
        )
    elif kind == "crypto":
        asset = PortfolioAsset(
            kind="crypto",
            name=(req.name or "").strip(),
            chain=(req.chain or "").strip().lower() or None,
            wallet=(req.wallet or "").strip() or None,
            token_address=(req.token_address or "").strip() or None,
            coingecko_id=(req.coingecko_id or "").strip().lower() or None,
            manual_quantity=(max(0.0, float(req.manual_quantity)) if req.manual_quantity is not None else None),
            category_id=cat,
            bucket_weight=bw,
        )
    elif kind == "cash":
        asset = PortfolioAsset(
            kind="cash",
            name=((req.name or "").strip() or "现金"),
            cash_amount_cny=max(0.0, float(req.cash_amount_cny or 0.0)),
            category_id=(cat or "cash"),
            bucket_weight=bw,
        )
    else:
        return JSONResponse({"ok": False, "error": "invalid kind"}, status_code=400)

    portfolio.assets.append(asset)
    save_portfolio(portfolio)
    trigger_cache_refresh(force=True)
    return JSONResponse({"ok": True, "asset": asset.model_dump()})


@app.patch("/api/v2/assets/{asset_id}")
async def api_v2_assets_update(asset_id: str, req: ApiAssetUpdateRequest) -> JSONResponse:
    asset_id = (asset_id or "").strip()
    if not asset_id:
        return JSONResponse({"ok": False, "error": "missing asset_id"}, status_code=400)

    portfolio = load_portfolio()
    target: PortfolioAsset | None = None
    for a in portfolio.assets:
        if a.id == asset_id:
            target = a
            break
    if target is None:
        return JSONResponse({"ok": False, "error": "asset not found"}, status_code=404)

    fs = set(req.model_fields_set)
    _apply_asset_patch(target=target, req=req, fields_set=fs)

    save_portfolio(portfolio)
    trigger_cache_refresh(force=True)
    return JSONResponse({"ok": True, "asset": target.model_dump()})


def _apply_asset_patch(*, target: PortfolioAsset, req: ApiAssetUpdateRequest, fields_set: set[str]) -> None:
    fs = set(fields_set or set())

    if target.kind == "cn":
        if "code" in fs:
            target.code = (req.code or "").strip()
        if "name" in fs:
            target.name = (req.name or "").strip()
        if "quantity" in fs and req.quantity is not None:
            target.quantity = max(0.0, float(req.quantity))
        if "category_id" in fs:
            target.category_id = (req.category_id or "").strip() or None
        if "bucket_weight" in fs:
            target.bucket_weight = _coerce_bucket_weight(req.bucket_weight)
        return

    if target.kind == "crypto":
        if "name" in fs:
            target.name = (req.name or "").strip()
        if "chain" in fs:
            target.chain = (req.chain or "").strip().lower() or None
        if "wallet" in fs:
            target.wallet = (req.wallet or "").strip() or None
        if "token_address" in fs:
            target.token_address = (req.token_address or "").strip() or None
        if "coingecko_id" in fs:
            target.coingecko_id = (req.coingecko_id or "").strip().lower() or None
        if "manual_quantity" in fs:
            target.manual_quantity = max(0.0, float(req.manual_quantity)) if req.manual_quantity is not None else None
        if "category_id" in fs:
            target.category_id = (req.category_id or "").strip() or None
        if "bucket_weight" in fs:
            target.bucket_weight = _coerce_bucket_weight(req.bucket_weight)
        return

    if target.kind == "cash":
        if "name" in fs:
            target.name = (req.name or "").strip() or "现金"
        if "cash_amount_cny" in fs and req.cash_amount_cny is not None:
            target.cash_amount_cny = max(0.0, float(req.cash_amount_cny))
        if "category_id" in fs:
            target.category_id = ((req.category_id or "").strip() or "cash")
        if "bucket_weight" in fs:
            target.bucket_weight = _coerce_bucket_weight(req.bucket_weight)


@app.post("/api/v2/assets/batch")
async def api_v2_assets_batch_update(items: list[ApiAssetBatchUpdateItem]) -> JSONResponse:
    portfolio = load_portfolio()
    assets_by_id = {a.id: a for a in portfolio.assets}

    updated: list[str] = []
    not_found: list[str] = []
    for it in items or []:
        asset_id = (it.asset_id or "").strip()
        if not asset_id:
            continue
        target = assets_by_id.get(asset_id)
        if target is None:
            not_found.append(asset_id)
            continue
        fs = set(it.model_fields_set)
        fs.discard("asset_id")
        if not fs:
            continue
        _apply_asset_patch(target=target, req=it, fields_set=fs)
        updated.append(asset_id)

    if updated:
        save_portfolio(portfolio)
        trigger_cache_refresh(force=True)
    return JSONResponse({"ok": True, "updated": updated, "not_found": not_found})


@app.delete("/api/v2/assets/{asset_id}")
async def api_v2_assets_delete(asset_id: str) -> JSONResponse:
    asset_id = (asset_id or "").strip()
    if not asset_id:
        return JSONResponse({"ok": False, "error": "missing asset_id"}, status_code=400)
    portfolio = load_portfolio()
    before = len(portfolio.assets)
    portfolio.assets = [a for a in portfolio.assets if a.id != asset_id]
    if len(portfolio.assets) == before:
        return JSONResponse({"ok": False, "error": "asset not found"}, status_code=404)
    save_portfolio(portfolio)
    trigger_cache_refresh(force=True)
    return JSONResponse({"ok": True})


@app.post("/api/v2/assets/{asset_id}/move")
async def api_v2_assets_move(asset_id: str, req: ApiMoveRequest) -> JSONResponse:
    asset_id = (asset_id or "").strip()
    if not asset_id:
        return JSONResponse({"ok": False, "error": "missing asset_id"}, status_code=400)
    portfolio = load_portfolio()
    moved = False
    for a in portfolio.assets:
        if a.id == asset_id:
            a.category_id = (req.category_id or "").strip() or None
            moved = True
            break
    if not moved:
        return JSONResponse({"ok": False, "error": "asset not found"}, status_code=404)
    save_portfolio(portfolio)
    trigger_cache_refresh(force=True)
    return JSONResponse({"ok": True})


@app.get("/api/total-history")
async def api_total_history(request: Request) -> JSONResponse:
    window = request.query_params.get("window", "24h").strip()
    max_points_raw = request.query_params.get("max_points", "").strip()
    max_points = 240
    try:
        if max_points_raw:
            max_points = max(10, min(2000, int(max_points_raw)))
    except Exception:
        max_points = 240

    seconds = parse_window_seconds(window)

    # Cache points in memory to avoid re-parsing snapshots.jsonl on every page load.
    # Snapshots append at most once per minute, so a short cache TTL is safe.
    now_epoch = time.time()
    snap_mtime = SNAPSHOT_PATH.stat().st_mtime if SNAPSHOT_PATH.exists() else None
    cache_key = f"{seconds}:{max_points}"
    points = None
    try:
        if (
            runtime_cache.total_history_key == cache_key
            and runtime_cache.total_history_points is not None
            and runtime_cache.total_history_snap_mtime == snap_mtime
            and runtime_cache.total_history_loaded_at is not None
            and (now_epoch - runtime_cache.total_history_loaded_at) < 10.0
        ):
            points = runtime_cache.total_history_points
    except Exception:
        points = None

    if points is None:
        points = load_total_history_points(path=SNAPSHOT_PATH, since_seconds=seconds, max_points=max_points)
        runtime_cache.total_history_key = cache_key
        runtime_cache.total_history_points = points
        runtime_cache.total_history_loaded_at = now_epoch
        runtime_cache.total_history_snap_mtime = snap_mtime

    current_total = float(runtime_cache.view.total_value) if runtime_cache.view is not None else None
    payload = build_total_history_payload(points=points, current_value=current_total, window=window)
    return JSONResponse(payload)


@app.get("/api/ui/ledger-days")
async def api_ui_ledger_days(request: Request) -> JSONResponse:
    from zoneinfo import ZoneInfo

    portfolio = get_portfolio_cached()
    tz = ZoneInfo(settings.timezone)
    entries = load_ledger()
    manage = request.query_params.get("manage", "").strip().lower() in {"1", "true", "yes", "y", "on"}

    def _fmt_day(ts: float) -> str:
        try:
            return datetime.fromtimestamp(float(ts), tz=tz).date().isoformat()
        except Exception:
            return ""

    asset_name_by_id: dict[str, str] = {}
    if manage:
        view = runtime_cache.view
        if view is not None:
            view_assets = []
            for c in view.categories:
                view_assets.extend(c.assets)
            view_assets.extend(view.unassigned)
            for av in view_assets:
                try:
                    name = (getattr(av, "name", "") or getattr(av, "code", "") or getattr(av, "coingecko_id", "") or getattr(av, "id", "")).strip()
                except Exception:
                    name = ""
                if name:
                    asset_name_by_id[str(getattr(av, "id", ""))] = name
        for a in portfolio.assets:
            if a.id in asset_name_by_id:
                continue
            name = (a.name or a.code or a.coingecko_id or a.id).strip()
            asset_name_by_id[a.id] = name

    category_name_by_id = {c.id: c.name for c in portfolio.categories}
    asset_category_by_id = {a.id: (a.category_id.strip() if a.category_id else None) for a in portfolio.assets}

    running_principal = 0.0
    day_map: dict[str, dict] = {}
    for e in entries:
        day = _fmt_day(e.ts)
        if not day:
            continue
        g = day_map.get(day)
        if g is None:
            g = {
                "date": day,
                "entry_count": 0,
                "deposit_total": 0.0,
                "withdraw_total": 0.0,
                "net_total": 0.0,
                "running_principal_end": 0.0,
                "buckets": [{"id": c.id, "name": c.name, "deposit": 0.0, "withdraw": 0.0, "net": 0.0} for c in portfolio.categories],
                "other": {"deposit": 0.0, "withdraw": 0.0, "net": 0.0},
            }
            if manage:
                g["entries"] = []
            day_map[day] = g

        signed = float(e.signed_amount())
        running_principal += signed

        g["entry_count"] += 1
        g["net_total"] += signed
        g["running_principal_end"] = running_principal
        if e.direction == "deposit":
            g["deposit_total"] += float(e.amount_cny)
        else:
            g["withdraw_total"] += float(e.amount_cny)

        if manage:
            g["entries"].append(
                {
                    "id": e.id,
                    "date": day,
                    "direction": e.direction,
                    "amount_cny": float(e.amount_cny),
                    "asset_id": e.asset_id,
                    "asset_name": (asset_name_by_id.get(e.asset_id or "", "（组合层）") if e.asset_id else "（组合层）"),
                    "note": (e.note or "").strip(),
                }
            )

        cat_id = asset_category_by_id.get(e.asset_id or "") if e.asset_id else None
        if cat_id and cat_id in category_name_by_id:
            b = None
            for it in g["buckets"]:
                if it.get("id") == cat_id:
                    b = it
                    break
            if b is not None:
                if e.direction == "deposit":
                    b["deposit"] += float(e.amount_cny)
                else:
                    b["withdraw"] += float(e.amount_cny)
                b["net"] += signed
        else:
            if e.direction == "deposit":
                g["other"]["deposit"] += float(e.amount_cny)
            else:
                g["other"]["withdraw"] += float(e.amount_cny)
            g["other"]["net"] += signed

    days = sorted(day_map.values(), key=lambda x: x.get("date") or "", reverse=True)
    return JSONResponse({"days": days})


@app.post("/api/v2/ledger")
async def api_v2_ledger_add(req: ApiLedgerCreateRequest) -> JSONResponse:
    from zoneinfo import ZoneInfo

    tz_name = settings.timezone
    tz = ZoneInfo(tz_name)

    ts = parse_date_input(raw=(req.date or ""), tz_name=tz_name)
    if ts is None:
        ts = float(datetime.now(tz=tz).timestamp())

    direction = (req.direction or "deposit").strip().lower()
    if direction not in {"deposit", "withdraw"}:
        direction = "deposit"

    amt = max(0.0, float(req.amount_cny or 0.0))
    if amt <= 0:
        return JSONResponse({"ok": False, "error": "amount must be > 0"}, status_code=400)

    aid = (req.asset_id or "").strip() or None
    note = (req.note or "").strip() or None

    entry = LedgerEntry(ts=float(ts), direction=direction, amount_cny=amt, asset_id=aid, note=note)
    add_ledger_entry(entry)
    return JSONResponse({"ok": True, "entry": entry.model_dump()})


@app.delete("/api/v2/ledger/{entry_id}")
async def api_v2_ledger_delete(entry_id: str) -> JSONResponse:
    ok = delete_ledger_entry(entry_id)
    if not ok:
        return JSONResponse({"ok": False, "error": "entry not found"}, status_code=404)
    return JSONResponse({"ok": True})


@app.get("/api/v2/ledger/metrics")
async def api_v2_ledger_metrics() -> JSONResponse:
    from zoneinfo import ZoneInfo

    portfolio = get_portfolio_cached()
    view = runtime_cache.view
    if view is None:
        await refresh_runtime_cache(force=True)
        view = runtime_cache.view
    if view is None:
        view = _empty_view(portfolio, "行情缓存尚未就绪，请稍后刷新页面。")

    tz = ZoneInfo(settings.timezone)
    now_ts = float(datetime.now(tz=tz).timestamp())
    entries = load_ledger()

    total_metrics = compute_metrics(entries=entries, now_ts=now_ts, current_value=float(view.total_value))

    entries_by_asset_id: dict[str, list[LedgerEntry]] = {}
    for e in entries:
        if e.asset_id:
            entries_by_asset_id.setdefault(e.asset_id, []).append(e)

    view_assets = []
    for c in view.categories:
        view_assets.extend(c.assets)
    view_assets.extend(view.unassigned)
    asset_view_by_id = {a.id: a for a in view_assets}

    per_asset = []
    for a in portfolio.assets:
        av = asset_view_by_id.get(a.id)
        current_value = float(av.value) if av is not None else 0.0
        m = compute_metrics(entries=entries_by_asset_id.get(a.id, []), now_ts=now_ts, current_value=current_value)
        name = (av.name if av and av.name else (a.name or a.code or a.coingecko_id or a.id)).strip()
        per_asset.append(
            {
                "id": a.id,
                "kind": (av.kind if av else a.kind),
                "code": (av.code if av else (a.code or a.coingecko_id or "")),
                "name": name,
                "principal": m.principal,
                "current_value": m.current_value,
                "profit": m.profit,
                "xirr_annual": m.xirr_annual,
            }
        )

    return JSONResponse({"currency": "CNY", "now_ts": now_ts, "total": asdict(total_metrics), "per_asset": per_asset})


@app.get("/api/v2/rebalance/balance-needed")
async def api_v2_rebalance_balance_needed() -> JSONResponse:
    portfolio = get_portfolio_cached()
    view = runtime_cache.view
    if view is None:
        await refresh_runtime_cache(force=True)
        view = runtime_cache.view
    if view is None:
        view = _empty_view(portfolio, "行情缓存尚未就绪，请稍后刷新页面。")

    from app.rebalance_suggest import compute_full_balance_cash_needed

    need = compute_full_balance_cash_needed(view=view)
    return JSONResponse({"balance_needed_cny": float(need)})


@app.get("/api/v2/allocation/suggest")
async def api_v2_allocation_suggest(contribution: float = 0.0, prefill: str | None = None) -> JSONResponse:
    contribution = max(0.0, float(contribution or 0.0))
    portfolio = get_portfolio_cached()
    view = runtime_cache.view
    if view is None:
        await refresh_runtime_cache(force=True)
        view = runtime_cache.view
    if view is None:
        view = _empty_view(portfolio, "行情缓存尚未就绪，请稍后刷新页面。")

    from app.rebalance_suggest import compute_contribution_suggestion

    prefill_assets = {}
    if prefill:
        try:
            prefill_assets = _coerce_prefill_assets(json.loads(prefill))
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid prefill"}, status_code=400)

    suggestion = compute_contribution_suggestion(
        view=view,
        contribution_amount_cny=contribution,
        prefill_assets=prefill_assets,
    )
    payload = asdict(suggestion)
    payload["ok"] = True
    return JSONResponse(payload)


@app.get("/api/v2/crypto/snapshot")
async def api_v2_crypto_snapshot() -> JSONResponse:
    portfolio = get_portfolio_cached()
    view = runtime_cache.view
    if view is None:
        await refresh_runtime_cache(force=True)
        view = runtime_cache.view
    if view is None:
        return JSONResponse({"ok": False, "error": "cache not ready"}, status_code=503)

    manual_map: dict[str, bool] = {}
    for a in portfolio.assets:
        if a.kind == "crypto":
            manual_map[a.id] = a.manual_quantity is not None

    assets: dict[str, float] = {}
    view_assets = []
    for c in view.categories:
        view_assets.extend(c.assets)
    view_assets.extend(view.unassigned)
    for av in view_assets:
        if av.kind != "crypto":
            continue
        if manual_map.get(av.id):
            continue
        val = float(av.value or 0.0)
        if val <= 0:
            continue
        assets[str(av.id)] = val

    return JSONResponse({"ok": True, "ts": time.time(), "assets": assets})


@app.get("/api/v2/allocation/suggest-after-crypto")
async def api_v2_allocation_suggest_after_crypto(
    contribution: float = 0.0,
    baseline: str | None = None,
    expected: str | None = None,
    slip_pct: float | None = None,
) -> JSONResponse:
    contribution = max(0.0, float(contribution or 0.0))
    portfolio = get_portfolio_cached()
    await refresh_runtime_cache(force=True)
    view = runtime_cache.view
    if view is None:
        view = _empty_view(portfolio, "行情缓存尚未就绪，请稍后刷新页面。")

    manual_map: dict[str, bool] = {}
    for a in portfolio.assets:
        if a.kind == "crypto":
            manual_map[a.id] = a.manual_quantity is not None

    baseline_assets = {}
    if baseline:
        try:
            baseline_assets = _coerce_prefill_assets(json.loads(baseline))
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid baseline"}, status_code=400)

    expected_assets = {}
    if expected:
        try:
            expected_assets = _coerce_prefill_assets(json.loads(expected))
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid expected"}, status_code=400)

    try:
        slip = float(slip_pct or 0.0)
    except Exception:
        slip = 0.0
    slip = max(0.0, min(0.2, slip))

    prefill_assets: dict[str, float] = {}
    prefill_total = 0.0
    view_assets = []
    for c in view.categories:
        view_assets.extend(c.assets)
    view_assets.extend(view.unassigned)

    for av in view_assets:
        if av.kind != "crypto":
            continue
        if manual_map.get(av.id):
            continue
        val = float(av.value or 0.0)
        if val <= 0:
            continue
        asset_id = str(av.id)
        base = float(baseline_assets.get(asset_id, 0.0))
        delta = val - base
        if delta <= 0:
            continue
        exp = float(expected_assets.get(asset_id, 0.0))
        if exp > 0:
            lower = exp * (1.0 - slip)
            upper = exp * (1.0 + slip)
            if delta < lower:
                used = delta
            elif delta > upper:
                used = upper
            else:
                used = exp
        else:
            used = delta
        if used <= 0:
            continue
        prefill_assets[asset_id] = used
        prefill_total += used

    remaining = max(0.0, contribution - prefill_total)

    from app.rebalance_suggest import compute_contribution_suggestion

    suggestion = compute_contribution_suggestion(
        view=view,
        contribution_amount_cny=remaining,
        prefill_assets=prefill_assets,
        prefill_in_view=True,
    )
    payload = asdict(suggestion)
    payload["ok"] = True
    payload["prefill_assets"] = prefill_assets
    payload["prefill_total"] = prefill_total
    payload["baseline_used"] = bool(baseline_assets)
    payload["expected_used"] = bool(expected_assets)
    payload["slip_pct"] = slip
    payload["contribution_total"] = contribution
    payload["contribution_remaining"] = remaining
    return JSONResponse(payload)


@app.post("/api/v2/allocation/apply")
async def api_v2_allocation_apply(req: ApiAllocationApplyRequest) -> JSONResponse:
    from zoneinfo import ZoneInfo

    contribution = max(0.0, float(req.contribution or 0.0))
    if contribution <= 0:
        return JSONResponse({"ok": False, "error": "contribution must be > 0"}, status_code=400)

    portfolio = load_portfolio()
    view = runtime_cache.view
    if view is None:
        await refresh_runtime_cache(force=True)
        view = runtime_cache.view
    if view is None:
        view = _empty_view(portfolio, "行情缓存尚未就绪，建议稍后再试。")

    from app.rebalance_suggest import compute_contribution_suggestion

    prefill_assets = _coerce_prefill_assets(req.prefill_assets)
    prefill_in_view = False
    if prefill_assets:
        await refresh_runtime_cache(force=True)
        view = runtime_cache.view or view
        prefill_in_view = True

    suggestion = compute_contribution_suggestion(
        view=view,
        contribution_amount_cny=contribution,
        prefill_assets=prefill_assets,
        prefill_in_view=prefill_in_view,
    )
    assets_by_id = {a.id: a for a in portfolio.assets}

    view_qty_by_id: dict[str, float] = {}
    view_status_by_id: dict[str, str] = {}
    try:
        view_assets = []
        for c in view.categories:
            view_assets.extend(c.assets)
        view_assets.extend(view.unassigned)
        for av in view_assets:
            try:
                view_status_by_id[str(av.id)] = str(av.status or "")
            except Exception:
                pass
            if av.quantity is None:
                continue
            q = float(av.quantity)
            if q >= 0 and q < float("inf"):
                view_qty_by_id[str(av.id)] = q
    except Exception:
        view_qty_by_id = {}
        view_status_by_id = {}

    applied_cn = 0
    applied_cash = 0
    applied_crypto_manual = 0
    applied_crypto_ledger = 0
    skipped = 0
    ledger_new: list[LedgerEntry] = []
    ledger_ts = float(datetime.now(tz=ZoneInfo(settings.timezone)).timestamp())

    # Ensure cash bucket has at least one cash asset if cash gets allocated
    has_cash_asset = any(a.kind == "cash" and (a.category_id or "cash") == "cash" for a in portfolio.assets)
    cash_alloc = next((c.allocate_amount for c in suggestion.categories if c.category_id == "cash"), 0.0)
    if cash_alloc > 0 and not has_cash_asset:
        portfolio.assets.append(PortfolioAsset(kind="cash", name="现金", cash_amount_cny=0.0, category_id="cash"))
        assets_by_id = {a.id: a for a in portfolio.assets}

    for cat in suggestion.categories:
        for s in cat.assets:
            if not s.asset_id:
                skipped += 1
                continue
            a = assets_by_id.get(s.asset_id)
            if not a:
                skipped += 1
                continue
            if a.kind == "cn":
                if s.est_quantity is None:
                    skipped += 1
                    continue
                a.quantity = float(a.quantity or 0.0) + float(s.est_quantity)
                applied_cn += 1
                if float(s.amount_cny or 0.0) > 0:
                    ledger_new.append(
                        LedgerEntry(
                            ts=ledger_ts,
                            direction="deposit",
                            amount_cny=float(s.amount_cny),
                            asset_id=a.id,
                            note="auto: apply allocation",
                        )
                    )
                continue
            if a.kind == "cash":
                a.cash_amount_cny = float(a.cash_amount_cny or 0.0) + float(s.amount_cny)
                applied_cash += 1
                if float(s.amount_cny or 0.0) > 0:
                    ledger_new.append(
                        LedgerEntry(
                            ts=ledger_ts,
                            direction="deposit",
                            amount_cny=float(s.amount_cny),
                            asset_id=a.id,
                            note="auto: apply allocation",
                        )
                    )
                continue
            if a.kind == "crypto":
                amt = float(s.amount_cny or 0.0)
                if s.est_quantity is None:
                    # No price => cannot estimate quantity; keep as "planned" record only.
                    if amt > 0:
                        applied_crypto_ledger += 1
                        ledger_new.append(
                            LedgerEntry(
                                ts=ledger_ts,
                                direction="deposit",
                                amount_cny=amt,
                                asset_id=a.id,
                                note="auto: apply allocation (crypto planned; missing price)",
                            )
                        )
                    else:
                        skipped += 1
                    continue

                # If user opted into manual_quantity, we can apply quantity changes.
                if a.manual_quantity is not None:
                    if s.est_quantity is None:
                        skipped += 1
                        continue
                    a.manual_quantity = float(a.manual_quantity or 0.0) + float(s.est_quantity)
                    applied_crypto_manual += 1
                    if amt > 0:
                        ledger_new.append(
                            LedgerEntry(
                                ts=ledger_ts,
                                direction="deposit",
                                amount_cny=amt,
                                asset_id=a.id,
                                note="auto: apply allocation (crypto manual_quantity)",
                            )
                        )
                    continue

                # Wallet-tracked crypto: to "apply to holdings", switch to manual_quantity using current cached quantity as baseline.
                status = (view_status_by_id.get(a.id) or "").lower()
                base_qty = view_qty_by_id.get(a.id)
                if status == "ok" and base_qty is not None:
                    # Wallet is readable; do not mutate quantity (wallet-tracked). Record ledger only.
                    if amt > 0:
                        applied_crypto_ledger += 1
                        ledger_new.append(
                            LedgerEntry(
                                ts=ledger_ts,
                                direction="deposit",
                                amount_cny=amt,
                                asset_id=a.id,
                                note="auto: apply allocation (crypto wallet-tracked)",
                            )
                        )
                    else:
                        skipped += 1
                    continue

                # Wallet not readable: fall back to manual_quantity so allocation can be applied deterministically.
                a.manual_quantity = max(0.0, float(base_qty or 0.0)) + float(s.est_quantity)
                applied_crypto_manual += 1
                if amt > 0:
                    ledger_new.append(
                        LedgerEntry(
                            ts=ledger_ts,
                            direction="deposit",
                            amount_cny=amt,
                            asset_id=a.id,
                            note="auto: apply allocation (crypto -> manual_quantity)",
                        )
                    )
                continue

            skipped += 1

    save_portfolio(portfolio)
    try:
        add_ledger_entries(ledger_new)
    except Exception:
        pass
    trigger_cache_refresh(force=True)
    return JSONResponse(
        {
            "ok": True,
            "applied": {
                "cn": applied_cn,
                "cash": applied_cash,
                "crypto_manual": applied_crypto_manual,
                "crypto_ledger": applied_crypto_ledger,
                "skipped": skipped,
            },
            "ledger_entries": len(ledger_new),
            "suggestion": asdict(suggestion),
        }
    )


def _empty_view(portfolio: Portfolio, warning: str) -> PortfolioView:
    cats: list[CategoryView] = []
    for c in portfolio.categories:
        cats.append(
            CategoryView(
                id=c.id,
                name=c.name,
                value=0.0,
                weight=0.0,
                target_weight=c.target_weight,
                min_weight=c.min_weight,
                max_weight=c.max_weight,
                status="ok",
                note="",
                assets=[],
            )
        )
    return PortfolioView(
        total_value=0.0,
        as_of=None,
        categories=cats,
        unassigned=[],
        rebalance_warnings=[],
        warnings=[warning] if warning else [],
    )


async def refresh_runtime_cache(*, force: bool = False) -> None:
    if runtime_cache.refresh_running:
        return

    if not force and runtime_cache.updated_at is not None:
        age = (datetime.now() - runtime_cache.updated_at).total_seconds()
        if age < _CACHE_MIN_REFRESH_GAP_SECONDS:
            return

    runtime_cache.refresh_running = True
    start = time.perf_counter()
    try:
        # Reload portfolio only when the file changes (avoid re-parsing on every refresh tick).
        mtime = PORTFOLIO_PATH.stat().st_mtime if PORTFOLIO_PATH.exists() else None
        if force or runtime_cache.portfolio is None or runtime_cache.portfolio_mtime != mtime:
            runtime_cache.portfolio = load_portfolio()
            runtime_cache.portfolio_mtime = PORTFOLIO_PATH.stat().st_mtime if PORTFOLIO_PATH.exists() else mtime

        portfolio = runtime_cache.portfolio or load_portfolio()
        view = await compute_portfolio_view(portfolio=portfolio, quotes=quotes, chain=chain)
        runtime_cache.view = view
        runtime_cache.updated_at = datetime.now()
        runtime_cache.last_error = None

        runtime_cache.snapshot_last_epoch = maybe_append_snapshot(
            view=view,
            last_epoch=runtime_cache.snapshot_last_epoch,
            min_interval_seconds=_CACHE_SNAPSHOT_INTERVAL_SECONDS,
        )
    except Exception as e:
        runtime_cache.last_error = f"{type(e).__name__}: {e}"
    finally:
        runtime_cache.last_duration_ms = (time.perf_counter() - start) * 1000.0
        runtime_cache.refresh_running = False


def trigger_cache_refresh(*, force: bool = False) -> None:
    asyncio.create_task(refresh_runtime_cache(force=force))


def get_portfolio_cached() -> Portfolio:
    # Keep server-side page renders cheap: avoid re-parsing portfolio.json on every navigation.
    mtime = PORTFOLIO_PATH.stat().st_mtime if PORTFOLIO_PATH.exists() else None
    if runtime_cache.portfolio is None or runtime_cache.portfolio_mtime != mtime:
        runtime_cache.portfolio = load_portfolio()
        runtime_cache.portfolio_mtime = PORTFOLIO_PATH.stat().st_mtime if PORTFOLIO_PATH.exists() else mtime
    return runtime_cache.portfolio


async def _cache_refresh_loop() -> None:
    while True:
        await refresh_runtime_cache(force=False)
        sleep_s = _CACHE_ACTIVE_REFRESH_INTERVAL_SECONDS
        try:
            if runtime_cache.last_access_at is None:
                sleep_s = _CACHE_IDLE_REFRESH_INTERVAL_SECONDS
            else:
                idle_s = (datetime.now() - runtime_cache.last_access_at).total_seconds()
                if idle_s >= _CACHE_IDLE_AFTER_SECONDS:
                    sleep_s = _CACHE_IDLE_REFRESH_INTERVAL_SECONDS
        except Exception:
            sleep_s = _CACHE_ACTIVE_REFRESH_INTERVAL_SECONDS
        await asyncio.sleep(sleep_s)


@app.get("/api/v2/settings")
async def api_v2_settings_get() -> JSONResponse:
    override = load_settings_override() or SettingsOverride()
    payload = {
        "ok": True,
        "override": _sanitize_settings_override_for_ui(override),
        "effective": effective_settings_dict(settings),
    }
    return JSONResponse(payload)


@app.post("/api/v2/settings")
async def api_v2_settings_update(req: ApiSettingsUpdateRequest) -> JSONResponse:
    global settings
    prev = load_settings_override() or SettingsOverride()

    from app.crypto_store import encrypt_str

    def _clean_str(v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def _clean_mail_to(v: list[str] | str | None) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            items = [x.strip() for x in v.split(",") if x.strip()]
            return items or None
        if isinstance(v, list):
            items = [str(x).strip() for x in v if str(x).strip()]
            return items or None
        return None

    smtp_password_enc = prev.smtp_password_enc
    if req.smtp_password is not None and str(req.smtp_password).strip():
        smtp_password_enc = encrypt_str(str(req.smtp_password).strip())

    notify_cooldown_minutes = prev.notify_cooldown_minutes
    if req.notify_cooldown_minutes is not None:
        try:
            notify_cooldown_minutes = max(1, int(req.notify_cooldown_minutes))
        except Exception:
            notify_cooldown_minutes = prev.notify_cooldown_minutes

    smtp_port = prev.smtp_port
    if req.smtp_port is not None:
        try:
            smtp_port = max(1, min(65535, int(req.smtp_port)))
        except Exception:
            smtp_port = prev.smtp_port

    slip_val = prev.crypto_slip_pct
    if req.crypto_slip_pct is not None:
        try:
            slip_val = float(req.crypto_slip_pct)
        except Exception:
            slip_val = prev.crypto_slip_pct
        if slip_val is not None:
            slip_val = max(0.0, min(20.0, slip_val))

    ov = SettingsOverride(
        timezone=_clean_str(req.timezone) if req.timezone is not None else prev.timezone,
        email_enabled=req.email_enabled if req.email_enabled is not None else prev.email_enabled,
        notify_cooldown_minutes=notify_cooldown_minutes,
        daily_job_time=_clean_str(req.daily_job_time) if req.daily_job_time is not None else prev.daily_job_time,
        crypto_slip_pct=slip_val,
        mail_from=_clean_str(req.mail_from) if req.mail_from is not None else prev.mail_from,
        mail_to=_clean_mail_to(req.mail_to) if req.mail_to is not None else prev.mail_to,
        smtp_host=_clean_str(req.smtp_host) if req.smtp_host is not None else prev.smtp_host,
        smtp_port=smtp_port,
        smtp_username=_clean_str(req.smtp_username) if req.smtp_username is not None else prev.smtp_username,
        smtp_password_enc=smtp_password_enc,
        smtp_use_starttls=req.smtp_use_starttls if req.smtp_use_starttls is not None else prev.smtp_use_starttls,
    )

    save_settings_override(ov)
    settings = Settings.load()
    _restart_scheduler()

    payload = {
        "ok": True,
        "override": _sanitize_settings_override_for_ui(ov),
        "effective": effective_settings_dict(settings),
    }
    return JSONResponse(payload)


@app.post("/api/v2/settings/test-email")
async def api_v2_settings_test_email() -> JSONResponse:
    from zoneinfo import ZoneInfo

    portfolio = load_portfolio()
    view = runtime_cache.view
    if view is None:
        await refresh_runtime_cache(force=True)
        view = runtime_cache.view
    if view is None:
        view = _empty_view(portfolio, "行情缓存尚未就绪，邮件内容可能不完整。")
    state = load_notification_state()

    today = datetime.now(tz=ZoneInfo(settings.timezone)).date()
    first = first_workday_of_month_cn(today)
    yyyymm = today.strftime("%Y-%m")

    sent_any = False

    # monthly
    if today == first and state.monthly_last_sent_yyyymm != yyyymm:
        ok, err = send_email(
            settings=settings,
            subject=f"永久投资组合：{yyyymm} 再平衡检查提醒（手动触发）",
            body=format_email_body(view),
        )
        if ok:
            state.monthly_last_sent_yyyymm = yyyymm
            state.last_error = None
            save_notification_state(state)
            sent_any = True
        else:
            state.last_error = err
            save_notification_state(state)
            return JSONResponse({"ok": False, "error": err or "send failed"}, status_code=500)

    # threshold
    if view.rebalance_warnings:
        payload = "".join([w + "\n" for w in sorted(view.rebalance_warnings)])
        wh = __import__("hashlib").sha256(payload.encode("utf-8")).hexdigest()
        if should_send_threshold(state=state, warnings_hash=wh, cooldown_minutes=settings.notify_cooldown_minutes):
            ok, err = send_email(
                settings=settings,
                subject="永久投资组合：触发再平衡阈值（手动触发）",
                body=format_email_body(view),
            )
            if ok:
                state.threshold_last_sent_epoch = datetime.now(tz=ZoneInfo(settings.timezone)).timestamp()
                state.threshold_last_hash = wh
                state.last_error = None
                save_notification_state(state)
                sent_any = True
            else:
                state.last_error = err
                save_notification_state(state)
                return JSONResponse({"ok": False, "error": err or "send failed"}, status_code=500)

    return JSONResponse({"ok": True, "sent_any": sent_any})


@app.on_event("startup")
async def _startup() -> None:
    _restart_scheduler()
    await refresh_runtime_cache(force=True)
    global _cache_task
    _cache_task = asyncio.create_task(_cache_refresh_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _scheduler
    global _cache_task
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _cache_task is not None:
        _cache_task.cancel()
        try:
            await _cache_task
        except asyncio.CancelledError:
            pass
        _cache_task = None
    await quotes.close()
    await chain.close()

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.chain import ChainProvider
from app.mailer import send_email
from app.notifications import (
    NotificationState,
    load_notification_state,
    save_notification_state,
    should_send_threshold,
)
from app.portfolio import load_portfolio
from app.quotes import QuoteProvider
from app.rebalance import PortfolioView, compute_portfolio_view
from app.settings import Settings


def _is_workday_cn(d: date) -> bool:
    try:
        from chinese_calendar import is_workday  # type: ignore

        return bool(is_workday(d))
    except Exception:
        return d.weekday() < 5


def first_workday_of_month_cn(d: date) -> date:
    start = d.replace(day=1)
    for i in range(0, 10):
        cand = start + timedelta(days=i)
        if _is_workday_cn(cand):
            return cand
    return start


def _warnings_hash(view: PortfolioView) -> str:
    h = hashlib.sha256()
    for w in sorted(view.rebalance_warnings):
        h.update(w.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def format_email_body(view: PortfolioView) -> str:
    def fmt_num(value, decimals: int) -> str:
        if value is None:
            return "—"
        try:
            s = f"{float(value):.{decimals}f}"
            return s.rstrip("0").rstrip(".")
        except Exception:
            return "—"

    lines: list[str] = []
    lines.append("永久投资组合检查结果（本邮件由本地追踪服务生成）")
    lines.append("")
    lines.append(f"组合总市值（估算，CNY）：{view.total_value:,.2f}")
    lines.append(f"数据时间：{view.as_of or '—'}")
    lines.append("")
    lines.append("四类资产桶：")
    for c in view.categories:
        tag = "OK" if c.status == "ok" else "REBALANCE"
        lines.append(
            f"- {c.name}: 市值={c.value:,.2f} 占比={c.weight:.1%} 目标={c.target_weight:.0%} 区间=[{c.min_weight:.0%},{c.max_weight:.0%}] {tag}"
        )
        for a in c.assets:
            price = "—" if a.price is None else fmt_num(a.price, 8 if a.kind == "crypto" else 4)
            chg = "—" if a.change_pct is None else f"{a.change_pct:+.2f}%"
            qty = "—" if a.quantity is None else fmt_num(a.quantity, 8)
            lines.append(f"  - {a.name} ({a.code}) 数量={qty} 现价={price} 涨跌幅={chg} 来源={a.source}")
    if view.unassigned:
        lines.append("")
        lines.append("未分配资产：")
        for a in view.unassigned:
            price = "—" if a.price is None else fmt_num(a.price, 8 if a.kind == "crypto" else 4)
            chg = "—" if a.change_pct is None else f"{a.change_pct:+.2f}%"
            qty = "—" if a.quantity is None else fmt_num(a.quantity, 8)
            lines.append(f"- {a.name} ({a.code}) 数量={qty} 现价={price} 涨跌幅={chg} 来源={a.source}")
    lines.append("")
    if view.warnings:
        lines.append("再平衡提醒：")
        for w in view.warnings:
            lines.append(f"- {w}")
    else:
        lines.append("再平衡提醒：未触发阈值。")
    return "\n".join(lines)


async def maybe_send_threshold_email(*, settings: Settings, quotes: QuoteProvider, chain: ChainProvider, reason: str) -> None:
    if not settings.email_enabled:
        return
    state = load_notification_state()
    portfolio = load_portfolio()
    view = await compute_portfolio_view(portfolio=portfolio, quotes=quotes, chain=chain)
    await maybe_send_threshold_email_for_view(settings=settings, view=view, reason=reason, state=state)


async def maybe_send_threshold_email_for_view(
    *,
    settings: Settings,
    view: PortfolioView,
    reason: str,
    state: NotificationState | None = None,
) -> None:
    if not settings.email_enabled:
        return
    state = state or load_notification_state()
    if not view.rebalance_warnings:
        return

    wh = _warnings_hash(view)
    if not should_send_threshold(state=state, warnings_hash=wh, cooldown_minutes=settings.notify_cooldown_minutes):
        return

    ok, err = send_email(
        settings=settings,
        subject=f"永久投资组合：触发再平衡阈值（{reason}）",
        body=format_email_body(view),
    )
    if ok:
        state.threshold_last_sent_epoch = datetime.now(tz=ZoneInfo(settings.timezone)).timestamp()
        state.threshold_last_hash = wh
        state.last_error = None
        save_notification_state(state)
    else:
        state.last_error = err
        save_notification_state(state)


async def daily_job(*, settings: Settings, quotes: QuoteProvider, chain: ChainProvider) -> None:
    if not settings.email_enabled:
        return
    today = datetime.now(tz=ZoneInfo(settings.timezone)).date()
    state = load_notification_state()

    portfolio = load_portfolio()
    view = await compute_portfolio_view(portfolio=portfolio, quotes=quotes, chain=chain)

    # 1) 每月第一个工作日：固定提醒查看
    first = first_workday_of_month_cn(today)
    yyyymm = today.strftime("%Y-%m")
    if today == first and state.monthly_last_sent_yyyymm != yyyymm:
        ok, err = send_email(
            settings=settings,
            subject=f"永久投资组合：{yyyymm} 再平衡检查提醒（第一个工作日）",
            body=format_email_body(view),
        )
        if ok:
            state.monthly_last_sent_yyyymm = yyyymm
            state.last_error = None
            save_notification_state(state)
        else:
            state.last_error = err
            save_notification_state(state)

    # 2) 若触发阈值：发提醒（带冷却）
    if view.rebalance_warnings:
        await maybe_send_threshold_email_for_view(settings=settings, view=view, reason="scheduled", state=state)


def start_scheduler(*, settings: Settings, quotes: QuoteProvider, chain: ChainProvider) -> AsyncIOScheduler:
    tz = ZoneInfo(settings.timezone)
    scheduler = AsyncIOScheduler(timezone=tz)
    hh, mm = settings.daily_job_time.split(":")
    scheduler.add_job(
        daily_job,
        trigger="cron",
        hour=int(hh),
        minute=int(mm),
        kwargs={"settings": settings, "quotes": quotes, "chain": chain},
        id="daily_job",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler

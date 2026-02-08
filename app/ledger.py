from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.portfolio import DATA_DIR

LEDGER_PATH = DATA_DIR / "ledger.json"


class LedgerEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = Field(..., ge=0, description="Epoch seconds in local timezone date")
    direction: Literal["deposit", "withdraw"] = "deposit"
    amount_cny: float = Field(..., ge=0)
    asset_id: str | None = None
    note: str | None = None

    def signed_amount(self) -> float:
        amt = float(self.amount_cny or 0.0)
        if self.direction == "withdraw":
            return -amt
        return amt

    def cashflow_for_xirr(self) -> float:
        # Investor perspective:
        # - deposit: cash out => negative
        # - withdraw: cash in  => positive
        return -self.signed_amount()


def load_ledger() -> list[LedgerEntry]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists():
        return []
    raw = LEDGER_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[LedgerEntry] = []
    for it in data:
        try:
            out.append(LedgerEntry.model_validate(it))
        except Exception:
            continue
    out.sort(key=lambda e: e.ts)
    return out


def save_ledger(entries: list[LedgerEntry]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entries_sorted = sorted(entries, key=lambda e: e.ts)
    LEDGER_PATH.write_text(
        json.dumps([e.model_dump() for e in entries_sorted], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_ledger_entry(entry: LedgerEntry) -> LedgerEntry:
    entries = load_ledger()
    entries.append(entry)
    save_ledger(entries)
    return entry


def add_ledger_entries(new_entries: list[LedgerEntry]) -> None:
    if not new_entries:
        return
    entries = load_ledger()
    entries.extend(new_entries)
    save_ledger(entries)


def delete_ledger_entry(entry_id: str) -> bool:
    entry_id = (entry_id or "").strip()
    if not entry_id:
        return False
    entries = load_ledger()
    new_entries = [e for e in entries if e.id != entry_id]
    if len(new_entries) == len(entries):
        return False
    save_ledger(new_entries)
    return True


def date_to_epoch_seconds(*, d: date, tz_name: str) -> float:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    dt = datetime.combine(d, time.min).replace(tzinfo=tz)
    return float(dt.timestamp())


def parse_date_input(*, raw: str, tz_name: str) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        d = date.fromisoformat(s)
    except Exception:
        return None
    return date_to_epoch_seconds(d=d, tz_name=tz_name)


def _xnpv(rate: float, cashflows: list[tuple[float, float]]) -> float:
    if not cashflows:
        return 0.0
    if rate <= -0.999999:
        return math.inf
    t0 = cashflows[0][0]
    out = 0.0
    for t, cf in cashflows:
        years = (t - t0) / (365.0 * 24.0 * 3600.0)
        out += cf / ((1.0 + rate) ** years)
    return out


def xirr(cashflows: list[tuple[float, float]]) -> float | None:
    """
    Money-weighted annualized return (XIRR).
    Cashflows are (epoch_seconds, amount), positive means cash-in.
    Returns rate as a fraction (e.g. 0.12 = 12%).
    """
    if not cashflows or len(cashflows) < 2:
        return None
    cashflows = sorted(cashflows, key=lambda x: x[0])

    has_pos = any(cf > 0 for _, cf in cashflows)
    has_neg = any(cf < 0 for _, cf in cashflows)
    if not (has_pos and has_neg):
        return None

    lo = -0.9999
    hi = 1.0
    f_lo = _xnpv(lo, cashflows)
    f_hi = _xnpv(hi, cashflows)

    # Expand hi until we bracket a root or give up.
    for _ in range(60):
        if math.isfinite(f_lo) and math.isfinite(f_hi) and f_lo * f_hi < 0:
            break
        hi *= 2.0
        if hi > 1e6:
            return None
        f_hi = _xnpv(hi, cashflows)
    else:
        return None

    # Bisection
    for _ in range(120):
        mid = (lo + hi) / 2.0
        f_mid = _xnpv(mid, cashflows)
        if not math.isfinite(f_mid):
            hi = mid
            continue
        if abs(f_mid) < 1e-8:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return (lo + hi) / 2.0


def build_cashflows_for_xirr(*, entries: list[LedgerEntry], now_ts: float, final_value: float) -> list[tuple[float, float]]:
    flows: list[tuple[float, float]] = []
    for e in entries:
        flows.append((float(e.ts), float(e.cashflow_for_xirr())))
    flows.append((float(now_ts), float(final_value)))
    flows.sort(key=lambda x: x[0])
    return flows


@dataclass(frozen=True)
class LedgerMetrics:
    principal: float
    current_value: float
    profit: float
    xirr_annual: float | None
    start_ts: float | None


def compute_metrics(*, entries: list[LedgerEntry], now_ts: float, current_value: float) -> LedgerMetrics:
    principal = 0.0
    start_ts: float | None = None
    for e in entries:
        principal += float(e.signed_amount())
        if start_ts is None or float(e.ts) < start_ts:
            start_ts = float(e.ts)

    current_value = float(current_value or 0.0)
    profit = current_value - principal

    rate: float | None = None
    try:
        flows = build_cashflows_for_xirr(entries=entries, now_ts=now_ts, final_value=current_value)
        rate = xirr(flows)
    except Exception:
        rate = None

    return LedgerMetrics(
        principal=principal,
        current_value=current_value,
        profit=profit,
        xirr_annual=rate,
        start_ts=start_ts,
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.portfolio import Portfolio
from app.rebalance import PortfolioView
from app.total_history import TotalPoint


@dataclass
class PortfolioRuntimeCache:
    portfolio: Portfolio | None = None
    portfolio_mtime: float | None = None

    view: PortfolioView | None = None
    updated_at: datetime | None = None
    last_duration_ms: float | None = None
    last_error: str | None = None

    snapshot_last_epoch: float | None = None
    refresh_running: bool = False

    # For adaptive refresh (reduce background work when nobody is using the UI).
    last_access_at: datetime | None = None

    # Total-history endpoint cache (avoid re-parsing snapshots.jsonl on every page load).
    total_history_key: str | None = None
    total_history_loaded_at: float | None = None
    total_history_snap_mtime: float | None = None
    total_history_points: list[TotalPoint] | None = None

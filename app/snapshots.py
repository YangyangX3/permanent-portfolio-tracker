from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.rebalance import PortfolioView

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_PATH = DATA_DIR / "snapshots.jsonl"


def _view_to_snapshot(view: PortfolioView, *, ts: float) -> dict[str, Any]:
    cats = []
    for c in view.categories:
        cats.append(
            {
                "id": c.id,
                "name": c.name,
                "value": round(float(c.value), 6),
                "weight": round(float(c.weight), 8),
                "target_weight": float(c.target_weight),
                "min_weight": float(c.min_weight),
                "max_weight": float(c.max_weight),
            }
        )
    return {
        "ts": ts,
        "as_of": view.as_of,
        "total_value": round(float(view.total_value), 6),
        "categories": cats,
        "rebalance_warnings": list(view.rebalance_warnings),
        "warnings": list(view.warnings),
    }


def maybe_append_snapshot(*, view: PortfolioView, last_epoch: float | None, min_interval_seconds: int = 60) -> float:
    now = time.time()
    if last_epoch is not None and (now - last_epoch) < min_interval_seconds:
        return last_epoch

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    snap = _view_to_snapshot(view, ts=now)
    with SNAPSHOT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    return now

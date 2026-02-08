from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TotalPoint:
    ts: float
    value: float


def parse_window_seconds(window: str) -> int:
    w = (window or "").strip().lower()
    if not w:
        return 24 * 60 * 60
    if w.endswith("h"):
        try:
            n = int(w[:-1])
            return max(1, n) * 60 * 60
        except Exception:
            return 24 * 60 * 60
    if w.endswith("d"):
        try:
            n = int(w[:-1])
            return max(1, n) * 24 * 60 * 60
        except Exception:
            return 24 * 60 * 60
    if w.isdigit():
        # treat as hours
        return max(1, int(w)) * 60 * 60
    return 24 * 60 * 60


def _downsample(points: list[TotalPoint], max_points: int) -> list[TotalPoint]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    step = int(math.ceil(len(points) / max_points))
    out = points[::step]
    # Ensure we always keep the last point for "current" value.
    if out and points and out[-1].ts != points[-1].ts:
        out.append(points[-1])
    return out


def load_total_history_points(
    *, path: Path, since_seconds: int, max_points: int = 240, now_epoch: float | None = None
) -> list[TotalPoint]:
    now = float(now_epoch or time.time())
    start_ts = now - float(max(1, int(since_seconds)))
    if not path.exists():
        return []

    file_size = path.stat().st_size
    if file_size <= 0:
        return []

    # Read from the end of the JSONL file and expand until we cover the window
    # (keeps CPU/IO low even if snapshots grow for months).
    chunk = 256 * 1024
    max_read = 8 * 1024 * 1024
    read_size = min(file_size, chunk)

    points: list[TotalPoint] = []
    earliest_in_buf: float | None = None

    with path.open("rb") as f:
        while True:
            f.seek(max(0, file_size - read_size))
            buf = f.read(read_size)

            if file_size > read_size:
                nl = buf.find(b"\n")
                if nl >= 0:
                    buf = buf[nl + 1 :]

            points = []
            earliest_in_buf = None
            for raw in buf.splitlines():
                if not raw or not raw.strip():
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                try:
                    ts = float(obj.get("ts") or 0.0)
                except Exception:
                    ts = 0.0
                if ts <= 0:
                    continue
                if earliest_in_buf is None or ts < earliest_in_buf:
                    earliest_in_buf = ts
                if ts < start_ts:
                    continue
                try:
                    val = float(obj.get("total_value"))
                except Exception:
                    continue
                points.append(TotalPoint(ts=ts, value=val))

            points.sort(key=lambda p: p.ts)

            have_window = earliest_in_buf is not None and earliest_in_buf <= start_ts
            at_file_start = read_size >= file_size
            if have_window or at_file_start:
                break
            if read_size >= max_read:
                break
            read_size = min(file_size, read_size * 2)

    return _downsample(points, max_points=max_points)


def build_total_history_payload(
    *,
    points: list[TotalPoint],
    current_value: float | None,
    now_epoch: float | None = None,
    window: str,
) -> dict:
    now = float(now_epoch or time.time())
    series = list(points)
    if current_value is not None:
        if not series or abs(series[-1].ts - now) > 0.5:
            series.append(TotalPoint(ts=now, value=float(current_value)))

    if not series:
        baseline = float(current_value or 0.0)
        current = float(current_value or 0.0)
    else:
        baseline = float(series[0].value)
        current = float(series[-1].value)

    change_value = current - baseline
    if baseline > 0:
        change_pct = (change_value / baseline * 100.0)
    else:
        change_pct = 0.0 if abs(change_value) < 1e-9 else None

    return {
        "window": window,
        "currency": "CNY",
        "baseline_value": baseline,
        "current_value": current,
        "change_value": change_value,
        "change_pct": change_pct,
        "points": [{"t": p.ts, "v": p.value} for p in series],
    }

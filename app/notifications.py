from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NOTIFY_PATH = DATA_DIR / "notifications.json"


class NotificationState(BaseModel):
    monthly_last_sent_yyyymm: str | None = None
    threshold_last_sent_epoch: float | None = None
    threshold_last_hash: str | None = None
    last_error: str | None = None


def load_notification_state() -> NotificationState:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTIFY_PATH.exists():
        st = NotificationState()
        save_notification_state(st)
        return st
    try:
        data = json.loads(NOTIFY_PATH.read_text(encoding="utf-8"))
        return NotificationState.model_validate(data)
    except Exception:
        st = NotificationState(last_error="failed to parse notifications.json")
        save_notification_state(st)
        return st


def save_notification_state(state: NotificationState) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTIFY_PATH.write_text(
        json.dumps(state.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def should_send_threshold(*, state: NotificationState, warnings_hash: str, cooldown_minutes: int) -> bool:
    now = time.time()
    if state.threshold_last_sent_epoch is None:
        return True
    if state.threshold_last_hash != warnings_hash:
        return True
    return (now - state.threshold_last_sent_epoch) >= max(1, cooldown_minutes) * 60


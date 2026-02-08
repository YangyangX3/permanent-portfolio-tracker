from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from pydantic import BaseModel, Field


def _get_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _get_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


def _get_str(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return default
    s = v.strip()
    return s if s else default


def _get_list(name: str) -> list[str]:
    v = os.environ.get(name)
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SETTINGS_OVERRIDE_PATH = DATA_DIR / "app_settings.json"


class SettingsOverride(BaseModel):
    timezone: str | None = None
    email_enabled: bool | None = None
    notify_cooldown_minutes: int | None = Field(None, ge=1)
    daily_job_time: str | None = None
    crypto_slip_pct: float | None = Field(None, ge=0, le=20)
    mail_from: str | None = None
    mail_to: list[str] | None = None

    smtp_host: str | None = None
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password_enc: str | None = None
    smtp_use_starttls: bool | None = None


def load_settings_override() -> SettingsOverride | None:
    try:
        if not SETTINGS_OVERRIDE_PATH.exists():
            return None
        raw = SETTINGS_OVERRIDE_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        return SettingsOverride.model_validate_json(raw)
    except Exception:
        return None


def save_settings_override(override: SettingsOverride) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_OVERRIDE_PATH.write_text(override.model_dump_json(indent=2), encoding="utf-8")


@dataclass(frozen=True)
class Settings:
    timezone: str
    email_enabled: bool
    notify_cooldown_minutes: int
    daily_job_time: str
    crypto_slip_pct: float

    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_starttls: bool

    mail_from: str | None
    mail_to: list[str]

    @staticmethod
    def load() -> "Settings":
        base = Settings(
            timezone=_get_str("PP_TIMEZONE", "Asia/Shanghai") or "Asia/Shanghai",
            email_enabled=_get_bool("PP_EMAIL_ENABLED", False),
            notify_cooldown_minutes=_get_int("PP_NOTIFY_COOLDOWN_MINUTES", 360),
            daily_job_time=_get_str("PP_DAILY_JOB_TIME", "09:05") or "09:05",
            crypto_slip_pct=max(0.0, min(20.0, _get_float("PP_CRYPTO_SLIP_PCT", 1.0))),
            smtp_host=_get_str("PP_SMTP_HOST"),
            smtp_port=_get_int("PP_SMTP_PORT", 587),
            smtp_username=_get_str("PP_SMTP_USERNAME"),
            smtp_password=_get_str("PP_SMTP_PASSWORD"),
            smtp_use_starttls=_get_bool("PP_SMTP_USE_STARTTLS", True),
            mail_from=_get_str("PP_MAIL_FROM"),
            mail_to=_get_list("PP_MAIL_TO"),
        )
        ov = load_settings_override()
        if not ov:
            return base
        # Only allow safe overrides (no smtp credentials here).
        from app.crypto_store import decrypt_str

        smtp_password = decrypt_str(ov.smtp_password_enc or "") if ov.smtp_password_enc else None
        return replace(
            base,
            timezone=ov.timezone or base.timezone,
            email_enabled=ov.email_enabled if ov.email_enabled is not None else base.email_enabled,
            notify_cooldown_minutes=ov.notify_cooldown_minutes or base.notify_cooldown_minutes,
            daily_job_time=ov.daily_job_time or base.daily_job_time,
            crypto_slip_pct=ov.crypto_slip_pct if ov.crypto_slip_pct is not None else base.crypto_slip_pct,
            mail_from=ov.mail_from if ov.mail_from is not None else base.mail_from,
            mail_to=ov.mail_to if ov.mail_to is not None else base.mail_to,
            smtp_host=ov.smtp_host if ov.smtp_host is not None else base.smtp_host,
            smtp_port=ov.smtp_port or base.smtp_port,
            smtp_username=ov.smtp_username if ov.smtp_username is not None else base.smtp_username,
            smtp_password=smtp_password if smtp_password is not None else base.smtp_password,
            smtp_use_starttls=ov.smtp_use_starttls if ov.smtp_use_starttls is not None else base.smtp_use_starttls,
        )


def effective_settings_dict(settings: Settings) -> dict:
    d = asdict(settings)
    d["smtp_password"] = "***" if d.get("smtp_password") else None
    return d

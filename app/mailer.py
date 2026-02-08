from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.settings import Settings


def send_email(*, settings: Settings, subject: str, body: str) -> tuple[bool, str | None]:
    if not settings.email_enabled:
        return False, "email disabled"
    if not settings.smtp_host or not settings.mail_from or not settings.mail_to:
        return False, "email not configured"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.mail_from
    msg["To"] = ", ".join(settings.mail_to)
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            if settings.smtp_use_starttls:
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


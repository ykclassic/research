from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings
from app.preferences.service import preferences_service
from app.services.supabase_auth import get_user


def deliver_scanner_alert(access_token: str, user_id: str, event_type: str, title: str, message: str) -> None:
    preferences = preferences_service.get_or_create(access_token, user_id)
    alerts = preferences.alert_preferences
    if not alerts.email_alerts_enabled or not settings.smtp_host or not settings.smtp_from_email:
        return
    user = get_user(access_token)
    recipient = str(user.get("email") or "").strip()
    if not recipient:
        return
    email = EmailMessage()
    email["From"] = settings.smtp_from_email
    email["To"] = recipient
    email["Subject"] = f"Market Research Alert: {title}"
    email.set_content(
        f"{message}\n\nEvent: {event_type}\n\nThis is research and decision-support information; it is not an execution instruction."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as server:
        if settings.smtp_starttls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(email)

"""Gmail SMTP delivery for OTP emails."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class EmailDeliveryError(AppError):
    """SMTP send failed."""


class EmailService:
    """Send transactional mail via configured SMTP (Gmail app password)."""

    @staticmethod
    def send_otp(*, to_email: str, code: str, username: str) -> None:
        if not settings.smtp_user or not settings.smtp_password.get_secret_value():
            raise EmailDeliveryError(
                "SMTP is not configured. Set SMTP_USER and SMTP_PASSWORD in .env."
            )

        from_addr = settings.smtp_from or settings.smtp_user
        message = EmailMessage()
        message["Subject"] = "Meridian verification code"
        message["From"] = from_addr
        message["To"] = to_email
        message.set_content(
            f"Hi {username},\n\n"
            f"Your Meridian verification code is: {code}\n\n"
            f"It expires in {settings.otp_expire_minutes} minutes.\n"
            "If you did not create an account, ignore this email.\n"
        )

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.ehlo()
                if settings.smtp_use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(
                    settings.smtp_user,
                    settings.smtp_password.get_secret_value(),
                )
                smtp.send_message(message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send OTP email")
            raise EmailDeliveryError("Could not send verification email.") from exc

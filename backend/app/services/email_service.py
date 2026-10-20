from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from html import escape
import smtplib
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger("ccms.email_service")

RESEND_API_URL = "https://api.resend.com/emails"


class EmailDeliveryError(Exception):
    """Raised when email delivery fails via the configured provider."""
    pass


class EmailSender(ABC):
    """Abstract interface for transactional email delivery."""

    @abstractmethod
    def send_verification_email(self, to_email: str, name: str, token: str) -> None:
        """Send account email verification instructions containing a secure single-use token."""
        pass


class ResendEmailSender(EmailSender):
    """Official Resend HTTP API adapter using minimal httpx client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.RESEND_API_KEY

    def send_verification_email(self, to_email: str, name: str, token: str) -> None:
        if not self.api_key or not self.api_key.strip():
            logger.error("Attempted to send verification email via Resend without RESEND_API_KEY configured")
            raise EmailDeliveryError("Resend API key is not configured. Please set RESEND_API_KEY.")

        verification_url = f"{settings.EMAIL_VERIFICATION_URL}?token={token}"
        safe_name = escape(name.strip() or "Student", quote=True)

        subject = "Verify your CCMS campus email address"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #1e3a8a;">Campus Complaint Management System</h2>
            <p>Hello {safe_name},</p>
            <p>Thank you for registering your student account. Please verify your email address to activate your account and log in.</p>
            <div style="margin: 28px 0; text-align: center;">
                <a href="{verification_url}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                    Verify Email Address
                </a>
            </div>
            <p style="font-size: 0.85rem; color: #6b7280;">This verification link will expire in {settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES} minutes and can only be used once.</p>
            <p style="font-size: 0.85rem; color: #6b7280;">If you did not register for a CCMS account, please disregard this email.</p>
        </div>
        """
        text_body = (
            f"Hello {safe_name},\n\n"
            f"Thank you for registering your student account on CCMS.\n"
            f"Please verify your email address by opening the following link in your browser:\n\n"
            f"{verification_url}\n\n"
            f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES} minutes and can only be used once.\n"
        )

        payload = {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(RESEND_API_URL, json=payload, headers=headers)
                if resp.status_code not in (200, 201):
                    logger.error("Resend API rejected email delivery (HTTP %d)", resp.status_code)
                    raise EmailDeliveryError(
                        f"Resend rejected email delivery with status {resp.status_code}."
                    )
                logger.info("Verification email dispatched successfully via Resend for recipient")
        except httpx.RequestError as exc:
            logger.error("Network error communicating with Resend HTTP API: %s", str(exc))
            raise EmailDeliveryError(f"Failed to reach email provider: {str(exc)}") from exc


class SmtpEmailSender(EmailSender):
    """Local sandbox SMTP sender compatible with Mailpit, Mailtrap, or local SMTP server."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = False,
    ):
        self.host = host or settings.SMTP_HOST
        self.port = port or settings.SMTP_PORT
        self.username = username or settings.SMTP_USERNAME
        self.password = password or settings.SMTP_PASSWORD
        self.use_tls = use_tls or settings.SMTP_USE_TLS

    def send_verification_email(self, to_email: str, name: str, token: str) -> None:
        verification_url = f"{settings.EMAIL_VERIFICATION_URL}?token={token}"
        safe_name = escape(name.strip() or "Student", quote=True)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Verify your CCMS campus email address"
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to_email

        text_content = (
            f"Hello {safe_name},\n\n"
            f"Please verify your CCMS account by opening:\n{verification_url}\n\n"
            f"Link expires in {settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES} minutes."
        )
        html_content = (
            f"<p>Hello {safe_name},</p>"
            f"<p>Please <a href='{verification_url}'>click here to verify your CCMS account</a>.</p>"
            f"<p>This link expires in {settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES} minutes.</p>"
        )

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10.0) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(self.username, [to_email], msg.as_string())
            logger.info("Verification email sent via sandbox SMTP to %s", to_email)
        except Exception as exc:
            logger.error("Failed to deliver verification email via SMTP: %s", str(exc))
            raise EmailDeliveryError(f"SMTP delivery failed: {str(exc)}") from exc


class MockEmailSender(EmailSender):
    """In-memory mock sender strictly for automated test suites."""

    def __init__(self):
        self.sent_emails: List[Dict[str, Any]] = []
        self.should_fail: bool = False

    def send_verification_email(self, to_email: str, name: str, token: str) -> None:
        if self.should_fail:
            raise EmailDeliveryError("Simulated mock email delivery failure.")
        self.sent_emails.append({
            "to_email": to_email,
            "name": name,
            "token": token,
        })

    def clear(self) -> None:
        self.sent_emails.clear()
        self.should_fail = False


# Module-level test override singleton
_test_sender: Optional[EmailSender] = None


def set_email_sender_for_testing(sender: Optional[EmailSender]) -> None:
    """Inject mock or custom email sender during automated tests."""
    global _test_sender
    _test_sender = sender


def get_email_sender() -> EmailSender:
    """Retrieve the configured email sender adapter based on application settings."""
    global _test_sender
    if _test_sender is not None:
        return _test_sender

    provider = (settings.EMAIL_PROVIDER or "mock").strip().lower()
    if provider == "resend":
        return ResendEmailSender()
    elif provider == "smtp":
        return SmtpEmailSender()
    else:
        return MockEmailSender()

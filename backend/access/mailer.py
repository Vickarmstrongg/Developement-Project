import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import settings

log = logging.getLogger("mailer")

def send_email(to: str, subject: str, body: str) -> None:
    """Send through Gmail SMTP. Without Gmail credentials in .env the email is
    printed in the server console instead, so you can copy invite links in dev."""
    if not (settings.GMAIL_ADDRESS and settings.GMAIL_APP_PASSWORD):
        print(f"\n--- EMAIL (Gmail not configured, not sent) ---\nTo: {to}\nSubject: {subject}\n\n{body}\n----------------------------------------\n")
        return

    msg = EmailMessage()
    msg["From"] = f"Byte & Bite <{settings.GMAIL_ADDRESS}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL(
            "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=20
        ) as server:
            server.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
            server.send_message(msg)
    except Exception:  # a mail failure must never crash the request
        log.exception("Failed to send email to %s", to)


def send_invite_email(to: str, full_name: str, role: str, raw_token: str) -> None:
    link = f"{settings.FRONTEND_URL}/set-password?token={raw_token}"
    send_email(
        to,
        "You have been invited to Byte & Bite",
        f"Hi {full_name},\n\n"
        f"You have been invited to Byte & Bite as a {role}.\n"
        f"Use the link below to confirm your email and choose your password. "
        f"It expires in {settings.INVITE_EXPIRE_HOURS} hours.\n\n{link}\n\n"
        "If you were not expecting this, you can ignore this email.",
    )


def send_reset_email(to: str, full_name: str, raw_token: str) -> None:
    link = f"{settings.FRONTEND_URL}/set-password?token={raw_token}"
    send_email(
        to,
        "Reset your Byte & Bite password",
        f"Hi {full_name},\n\n"
        f"Use the link below to choose a new password. "
        f"It expires in {settings.RESET_EXPIRE_MINUTES} minutes.\n\n{link}\n\n"
        "If you did not ask for this, you can ignore this email.",
    )
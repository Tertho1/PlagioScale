import contextlib
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def _get_smtp_config():
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        logger.warning("Invalid SMTP_PORT — falling back to 587")
        port = 587
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": port,
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("SMTP_FROM", "noreply@plagioscale.local"),
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
    }


@contextlib.contextmanager
def smtp_connection():
    """Yield a reusable SMTP connection for sending multiple emails in one session.

    Yields None when SMTP is not configured or the connection fails.
    """
    cfg = _get_smtp_config()
    if not cfg["host"]:
        logger.warning("SMTP not configured")
        yield None
        return
    ctx = ssl.create_default_context()
    try:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
        if cfg["use_tls"]:
            server.starttls(context=ctx)
        if cfg["user"]:
            server.login(cfg["user"], cfg["password"])
    except Exception as e:
        logger.error("Failed to connect to SMTP server %s:%s — %s", cfg["host"], cfg["port"], e)
        yield None
        return
    try:
        yield server
    finally:
        with contextlib.suppress(Exception):
            server.quit()


def _send_via(server, cfg, to: str, msg: MIMEMultipart) -> bool:
    try:
        server.sendmail(cfg["from_addr"], [to], msg.as_string())
        logger.info("Email sent to %s — %s", to, msg["Subject"])
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def _build_message(cfg, to: str, subject: str, body_text: str, body_html: Optional[str]) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = cfg["from_addr"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))
    return msg


def send_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """Send a single email (opens and closes its own SMTP connection)."""
    cfg = _get_smtp_config()
    if not cfg["host"]:
        logger.warning("SMTP not configured — skipping email to %s", to)
        return False

    msg = _build_message(cfg, to, subject, body_text, body_html)
    with smtp_connection() as server:
        if server is None:
            return False
        return _send_via(server, cfg, to, msg)


def send_bulk_emails_detailed(messages: list[tuple]) -> list[bool]:
    """Send multiple emails over ONE SMTP connection.

    Args:
        messages: list of (to, subject, body_text[, body_html]) tuples.

    Returns a list of success flags aligned with the input.
    """
    results: list[bool] = []
    with smtp_connection() as server:
        if server is None:
            return [False] * len(messages)
        cfg = _get_smtp_config()
        for item in messages:
            to, subject, body_text = item[0], item[1], item[2]
            body_html = item[3] if len(item) > 3 else None
            msg = _build_message(cfg, to, subject, body_text, body_html)
            results.append(_send_via(server, cfg, to, msg))
    return results


def send_bulk_emails(messages: list[tuple]) -> int:
    """Send multiple emails over one SMTP connection.

    Args:
        messages: list of (to, subject, body_text[, body_html]) tuples.

    Returns number of successfully sent emails.
    """
    return sum(send_bulk_emails_detailed(messages))


def notify_completion(to: str, name: str, batch_name: str, score: Optional[float] = None):
    subject = f"[PlagioScale] Analysis complete — {batch_name}"
    body = f"Hi {name},\n\nYour submission for '{batch_name}' has been analyzed."
    if score is not None:
        body += f"\nSimilarity score: {score:.1%}"
    body += "\n\nLog in to view the full results.\n— PlagioScale"
    send_email(to, subject, body)


def notify_assignment_open(to: str, name: str, batch_name: str, access_code: str):
    subject = f"[PlagioScale] New assignment — {batch_name}"
    body = (
        f"Hi {name},\n\n"
        f"A new assignment '{batch_name}' is open.\n"
        f"Access code: {access_code}\n\n"
        f"Submit your work at the submission portal.\n"
        f"— PlagioScale"
    )
    send_email(to, subject, body)

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def _get_smtp_config():
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("SMTP_FROM", "noreply@plagioscale.local"),
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
    }


def send_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    cfg = _get_smtp_config()
    if not cfg["host"]:
        logger.warning("SMTP not configured — skipping email to %s", to)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = cfg["from_addr"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            if cfg["use_tls"]:
                server.starttls(context=ctx)
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_addr"], [to], msg.as_string())
        logger.info("Email sent to %s — %s", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


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

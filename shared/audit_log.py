"""Audit logging for PlagioScale — structured JSON logs of all state-changing actions."""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone

AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "")

_audit_logger = logging.getLogger("plagioscale.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False

if not _audit_logger.handlers:
    log_dir = os.path.dirname(AUDIT_LOG_PATH) if AUDIT_LOG_PATH else ""
    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
        except (OSError, PermissionError):
            log_dir = ""
    if not log_dir:
        log_dir = tempfile.mkdtemp(prefix="plagioscale_audit_")
        AUDIT_LOG_PATH = os.path.join(log_dir, "audit.log")
    handler = logging.FileHandler(AUDIT_LOG_PATH)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(handler)


def audit(action: str, actor: str = None, resource: str = None, detail: dict = None) -> None:
    """Write a structured audit log entry.

    Args:
        action: Action performed (e.g. 'submission.create', 'assignment.create', 'auth.login')
        actor: User ID or 'system' for automated actions
        resource: Resource identifier (e.g. submission_id, batch_id)
        detail: Optional dict with additional context
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor or "anonymous",
        "resource": resource or "",
        "detail": detail or {},
    }
    _audit_logger.info(json.dumps(entry))

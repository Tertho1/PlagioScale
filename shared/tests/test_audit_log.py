"""Tests for audit logging module."""
import json
import logging
import os
import tempfile
from unittest.mock import patch, MagicMock
import shared.audit_log


def test_audit_writes_log_entry():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_path = f.name
    with patch("shared.audit_log.AUDIT_LOG_PATH", log_path):
        handler = logging.FileHandler(log_path)
        old_handlers = shared.audit_log._audit_logger.handlers[:]
        shared.audit_log._audit_logger.handlers = [handler]
        try:
            shared.audit_log.audit("test.action", actor="user_1", resource="res_1", detail={"key": "val"})
        finally:
            shared.audit_log._audit_logger.handlers = old_handlers
            handler.close()

    with open(log_path) as f:
        line = f.readline()
    os.unlink(log_path)

    entry = json.loads(line)
    assert entry["action"] == "test.action"
    assert entry["actor"] == "user_1"
    assert entry["resource"] == "res_1"
    assert entry["detail"] == {"key": "val"}
    assert "timestamp" in entry


def test_audit_defaults():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_path = f.name
    handler = logging.FileHandler(log_path)
    old_handlers = shared.audit_log._audit_logger.handlers[:]
    shared.audit_log._audit_logger.handlers = [handler]
    try:
        shared.audit_log.audit("test.no_args")
    finally:
        shared.audit_log._audit_logger.handlers = old_handlers
        handler.close()

    with open(log_path) as f:
        line = f.readline()
    os.unlink(log_path)

    entry = json.loads(line)
    assert entry["action"] == "test.no_args"
    assert entry["actor"] == "anonymous"
    assert entry["resource"] == ""
    assert entry["detail"] == {}


def test_audit_creates_log_dir():
    with patch("shared.audit_log._audit_logger.handlers", []):
        with patch("os.makedirs") as mock_makedirs:
            import importlib
            importlib.reload(shared.audit_log)
            mock_makedirs.assert_called_once()

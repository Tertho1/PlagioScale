"""Tests for email notification module."""
import os
from unittest.mock import patch

from shared.email_notifier import notify_assignment_open, notify_completion, send_bulk_emails, send_email


def test_send_email_no_smtp_config():
    os.environ.pop("SMTP_HOST", None)
    assert send_email("test@example.com", "Subj", "Body") is False


def test_send_email_success():
    os.environ["SMTP_HOST"] = "smtp.example.com"
    os.environ["SMTP_PORT"] = "587"
    os.environ["SMTP_USER"] = "user"
    os.environ["SMTP_PASSWORD"] = "pass"
    with patch("shared.email_notifier.smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value
        result = send_email("to@example.com", "Test", "Hello")
    assert result is True
    instance.sendmail.assert_called_once()
    instance.quit.assert_called_once()


def test_send_bulk_emails():
    os.environ["SMTP_HOST"] = "smtp.example.com"
    with patch("shared.email_notifier.smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value
        sent = send_bulk_emails([
            ("a@example.com", "Subj A", "Body A"),
            ("b@example.com", "Subj B", "Body B"),
        ])
    assert sent == 2
    assert instance.sendmail.call_count == 2


def test_send_email_with_html():
    os.environ["SMTP_HOST"] = "smtp.example.com"
    with patch("shared.email_notifier.smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value
        result = send_email("to@example.com", "Test", "Hello", "<p>Hello</p>")
    assert result is True
    instance.sendmail.assert_called_once()


def test_send_email_no_tls(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    with patch("shared.email_notifier.smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value
        result = send_email("to@example.com", "Test", "Hello")
    assert result is True
    instance.starttls.assert_not_called()


def test_send_email_smtp_failure(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    with patch("shared.email_notifier.smtplib.SMTP", side_effect=Exception("Connection refused")):
        result = send_email("to@example.com", "Test", "Hello")
    assert result is False


def test_notify_completion():
    with patch("shared.email_notifier.send_email") as mock_send:
        notify_completion("to@test.com", "Alice", "Assignment 1", score=0.85)
    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert "to@test.com" == args[0]
    assert "Assignment 1" in args[1]
    assert "85.0%" in args[2]


def test_notify_assignment_open():
    with patch("shared.email_notifier.send_email") as mock_send:
        notify_assignment_open("to@test.com", "Bob", "HW2", "CODE123")
    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert "to@test.com" == args[0]
    assert "HW2" in args[1]
    assert "CODE123" in args[2]

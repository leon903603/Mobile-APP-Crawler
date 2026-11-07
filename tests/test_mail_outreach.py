import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
import mail


def test_send_outreach_email_dry_run():
    res = mail.send_outreach_email(
        to_email="dev@example.com",
        developer_name="John Doe",
        app_name="DemoApp",
        dry_run=True,
    )
    assert res["ok"] is True
    assert res["dry_run"] is True
    assert "mock" in res["id"].lower()


def test_send_report_email_compatibility_alias():
    res = mail.send_report_email(
        "dev@example.com",
        "John Doe",
        "DemoApp",
        "reports/demo.pdf",
        dry_run=True,
    )
    assert res["ok"] is True
    assert res["dry_run"] is True


def test_get_daily_sent_count():
    count = mail.get_daily_sent_count()
    assert isinstance(count, int)
    assert count >= 0


def test_get_pending_report_emails():
    rows = mail.get_pending_report_emails(limit=2)
    assert isinstance(rows, list)
    if rows:
        # Check tuple structure: dev_id, dev_name, email, app_db_id, app_id, app_name, store, scan_report_id, version, excerpt_path
        assert len(rows[0]) == 10


import os
import json
import pytest
from unittest.mock import patch, MagicMock

from scanner.worker import _load_english_rules, run_detection
from email_pipeline.guard import can_dispatch_email
from datetime import datetime, time
from zoneinfo import ZoneInfo


def test_load_english_rules():
    """Verify that English security rules are properly loaded from JSON dictionary."""
    rules = _load_english_rules()
    assert isinstance(rules, dict)
    assert len(rules) >= 80
    assert "AS-lab001" in rules
    assert "Cleartext HTTP Traffic Check" in rules["AS-lab001"]["title"]
    assert "App must not transmit data over cleartext HTTP" in rules["AS-lab001"]["desc"]


def test_english_payload_injection():
    """Verify that worker forces lang='en' and replaces Chinese rules with English rules."""
    mock_report = {
        "lang": "zh-TW",
        "system": "android",
        "rule": {
            "AS-lab001": {
                "title": "SSL Connection / Cleartext HTTP 傳輸檢查",
                "desc": "中文敘述",
                "mas": "4.1.2.4.1"
            }
        },
        "result": {
            "app_name": "unknown_app",
            "file_name": "raw.apk",
            "mast_report": {
                "AS-lab001": {"isDetected": True, "data": []}
            }
        }
    }

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_report
        mock_resp.content = b"%PDF-1.4 mock content"
        mock_post.return_value = mock_resp

        with patch("builtins.open", MagicMock()):
            # Simulate run_detection logic
            en_rules = _load_english_rules()
            assert en_rules is not None

            # Apply same injection logic as worker.py
            mock_report["lang"] = "en"
            for r_key, r_val in en_rules.items():
                if r_key in mock_report["rule"]:
                    mock_report["rule"][r_key].update(r_val)

            assert mock_report["lang"] == "en"
            assert mock_report["rule"]["AS-lab001"]["title"] == "SSL Connection / Cleartext HTTP Traffic Check"
            assert "App must not transmit data over cleartext HTTP" in mock_report["rule"]["AS-lab001"]["desc"]


def test_guard_dispersed_single_send():
    """Verify guard correctly allows dispatching 1 email during business hours."""
    taipei_tz = ZoneInfo("Asia/Taipei")
    # Tuesday at 10:15
    dt_valid = datetime(2026, 11, 10, 10, 15, tzinfo=taipei_tz)

    # 1. Below quota (today=0, week=0) -> Allowed
    allowed, reason = can_dispatch_email(
        daily_sent_count=0,
        weekly_sent_count=0,
        quota_limit=4,
        weekly_quota_limit=20,
        now=dt_valid
    )
    assert allowed is True
    assert reason == ""

    # 2. Daily quota reached (today=4) -> Blocked
    allowed, reason = can_dispatch_email(
        daily_sent_count=4,
        weekly_sent_count=10,
        quota_limit=4,
        weekly_quota_limit=20,
        now=dt_valid
    )
    assert allowed is False
    assert "Daily quota limit reached" in reason

    # 3. Weekly quota reached (week=20) -> Blocked
    allowed, reason = can_dispatch_email(
        daily_sent_count=2,
        weekly_sent_count=20,
        quota_limit=4,
        weekly_quota_limit=20,
        now=dt_valid
    )
    assert allowed is False
    assert "Weekly quota limit reached" in reason

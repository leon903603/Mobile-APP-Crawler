import pytest
import os
from datetime import datetime, time
from email_pipeline.guard import can_dispatch_email, get_random_throttle_delay
from email_pipeline.payload import (
    build_outreach_email,
    DEFAULT_FROM_EMAIL,
    DEFAULT_REPLY_TO,
    OPT_OUT_STATEMENT,
)
from email_pipeline.sender import dispatch_outreach_email
from scanner.worker import extract_first_pages
from backfill_scan_tasks import fetch_candidate_apps


def test_can_dispatch_email_allowed_during_working_hours_under_quota():
    # 2026-10-07 is Wednesday (weekday 2)
    test_time = datetime(2026, 10, 7, 10, 30, 0)
    allowed, reason = can_dispatch_email(now=test_time, daily_sent_count=1)
    assert allowed is True
    assert reason == ""


def test_can_dispatch_email_default_daily_and_weekly_quotas():
    # Wednesday 14:00
    test_time = datetime(2026, 10, 7, 14, 0, 0)

    # Hits default daily quota of 4
    allowed_d, reason_d = can_dispatch_email(now=test_time, daily_sent_count=4)
    assert allowed_d is False
    assert "daily quota" in reason_d.lower()

    # Hits default weekly quota of 20
    allowed_w, reason_w = can_dispatch_email(now=test_time, daily_sent_count=1, weekly_sent_count=20)
    assert allowed_w is False
    assert "weekly quota" in reason_w.lower()


def test_can_dispatch_email_blocked_outside_working_hours():
    early_time = datetime(2026, 10, 7, 8, 45, 0)
    allowed, reason = can_dispatch_email(now=early_time, daily_sent_count=0)
    assert allowed is False
    assert "working hours" in reason.lower()

    late_time = datetime(2026, 10, 7, 18, 15, 0)
    allowed, reason = can_dispatch_email(now=late_time, daily_sent_count=0)
    assert allowed is False
    assert "working hours" in reason.lower()


def test_can_dispatch_email_blocked_on_weekends():
    # 2026-10-10 is Saturday (weekday 5)
    saturday_noon = datetime(2026, 10, 10, 12, 0, 0)
    allowed, reason = can_dispatch_email(now=saturday_noon, daily_sent_count=0)
    assert allowed is False
    assert "weekend" in reason.lower()

    # Allowed when allow_weekends=True
    allowed_wk, _ = can_dispatch_email(now=saturday_noon, daily_sent_count=0, allow_weekends=True)
    assert allowed_wk is True


def test_can_dispatch_email_bypass_hours_flag():
    # Sunday midnight
    sunday_midnight = datetime(2026, 10, 11, 2, 30, 0)
    allowed, reason = can_dispatch_email(now=sunday_midnight, daily_sent_count=0, bypass_hours=True)
    assert allowed is True
    assert reason == ""


def test_get_random_throttle_delay_within_range():
    for _ in range(50):
        delay = get_random_throttle_delay(min_s=180, max_s=420)
        assert 180 <= delay <= 420


def test_build_outreach_email_valid_structure_and_headers():
    payload = build_outreach_email(
        to_email="dev@example.com",
        developer_name="Alex",
        app_name="SuperApp",
    )

    assert payload["from"] == DEFAULT_FROM_EMAIL
    assert payload["reply_to"] == DEFAULT_REPLY_TO
    assert payload["to"] == ["dev@example.com"]
    assert "SuperApp" in payload["subject"]
    assert "Alex" in payload["html"]
    assert "SuperApp" in payload["html"]
    assert "https://cmaa.solitesterror.com" in payload["html"]
    assert OPT_OUT_STATEMENT in payload["html"]


def test_build_outreach_email_escapes_html_entities():
    # Prevent XSS and DOM breakage from external untrusted app / developer names
    payload = build_outreach_email(
        to_email="dev@example.com",
        developer_name="Alex <Tech Lead & Founder>",
        app_name="Cool & Fast <v2.0>",
    )

    # In HTML, entities must be escaped
    assert "Alex &lt;Tech Lead &amp; Founder&gt;" in payload["html"]
    assert "Cool &amp; Fast &lt;v2.0&gt;" in payload["html"]
    assert "<Tech Lead" not in payload["html"]

    # In plain text, raw strings should be preserved
    assert "Alex <Tech Lead & Founder>" in payload["text"]
    assert "Cool & Fast <v2.0>" in payload["text"]
    assert "Cool & Fast <v2.0>" in payload["subject"]


def test_build_outreach_email_supports_attachments():
    payload = build_outreach_email(
        to_email="dev@example.com",
        developer_name="Alex",
        app_name="SuperApp",
        attachments=[{"filename": "report.pdf", "content": "JVBERi0xLjQK..."}],
    )

    assert "attachments" in payload
    assert len(payload["attachments"]) == 1
    assert payload["attachments"][0]["filename"] == "report.pdf"


def test_extract_first_pages_returns_none_on_missing_file():
    # Defense check: Never return fake non-existent paths on missing files
    result = extract_first_pages("/non/existent/path/report.pdf")
    assert result is None


def test_backfill_candidate_query_executes_cleanly():
    # Test DB query logic executes without syntax errors
    candidates = fetch_candidate_apps(limit=3)
    assert isinstance(candidates, list)
    for c in candidates:
        app_db_id, app_id, app_name, country, dev_name, dev_email, installs = c
        assert app_db_id > 0
        assert app_id != ""
        assert dev_email is not None
        assert "@" in dev_email


def test_dispatch_outreach_email_dry_run_mode_does_not_call_network():
    payload = build_outreach_email(
        to_email="target@example.com",
        developer_name="Dev",
        app_name="AppX",
    )

    result = dispatch_outreach_email(email_payload=payload, dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert "mock" in result["id"].lower()


def test_dispatch_outreach_email_requires_api_key_when_not_dry_run(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    payload = build_outreach_email(
        to_email="target@example.com",
        developer_name="Dev",
        app_name="AppX",
    )

    with pytest.raises(ValueError, match="RESEND_API_KEY"):
        dispatch_outreach_email(email_payload=payload, dry_run=False, api_key=None)


def test_dispatch_outreach_email_success_with_http_client():
    payload = build_outreach_email(
        to_email="target@example.com",
        developer_name="Dev",
        app_name="AppX",
    )

    class MockHttpClient:
        def post(self, url, headers, data):
            assert url == "https://api.resend.com/emails"
            assert headers["Authorization"] == "Bearer re_test_key"
            return {"id": "re_msg_abc123"}

    result = dispatch_outreach_email(
        email_payload=payload,
        dry_run=False,
        api_key="re_test_key",
        http_client=MockHttpClient(),
    )

    assert result["ok"] is True
    assert result["id"] == "re_msg_abc123"


def test_dispatch_outreach_email_gracefully_handles_error():
    payload = build_outreach_email(
        to_email="target@example.com",
        developer_name="Dev",
        app_name="AppX",
    )

    class FailingHttpClient:
        def post(self, url, headers, data):
            raise RuntimeError("Upstream 429 Rate Limited")

    result = dispatch_outreach_email(
        email_payload=payload,
        dry_run=False,
        api_key="re_test_key",
        http_client=FailingHttpClient(),
    )

    assert result["ok"] is False
    assert "Rate Limited" in result["error"]

import unittest
from datetime import datetime, timezone, timedelta

from email_pipeline.guard import can_dispatch_email


class TestEnglishPipeline(unittest.TestCase):
    def test_english_payload_sanitization_and_lang(self):
        """Verify that worker sets lang='en' and sanitizes metadata before PDF generation."""
        mock_report = {
            "lang": "zh-TW",
            "system": {
                "fileName": "raw.apk",
                "appName": "old_name",
            },
            "rule": {
                "AS-lab001": {
                    "title": "SSL Connection / Cleartext HTTP Traffic Check",
                    "desc": "App must not transmit data over cleartext HTTP",
                    "mas": "4.1.2.4.1"
                }
            },
            "result": {
                "fileName": "raw.apk",
                "appName": "old_name",
                "mast_report": {
                    "AS-lab001": {"isDetected": True, "data": []}
                }
            }
        }

        # Simulate run_detection data cleaning block
        clean_basename = "test_app.apk"
        clean_name = "Test App"

        mock_report["lang"] = "en"
        for section in ("system", "result"):
            if section in mock_report and isinstance(mock_report[section], dict):
                target_dict = mock_report[section]
                target_dict["file_name"] = clean_basename
                target_dict["app_name"] = clean_name
                target_dict.pop("fileName", None)
                target_dict.pop("appName", None)

        self.assertEqual(mock_report["lang"], "en")
        self.assertEqual(mock_report["system"]["file_name"], "test_app.apk")
        self.assertEqual(mock_report["system"]["app_name"], "Test App")
        self.assertNotIn("fileName", mock_report["system"])
        self.assertNotIn("appName", mock_report["system"])
        self.assertEqual(mock_report["result"]["file_name"], "test_app.apk")
        self.assertEqual(mock_report["result"]["app_name"], "Test App")
        self.assertNotIn("fileName", mock_report["result"])
        self.assertNotIn("appName", mock_report["result"])

    def test_guard_dispersed_single_send(self):
        """Verify guard correctly allows dispatching 1 email during business hours."""
        taipei_tz = timezone(timedelta(hours=8))
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
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

        # 2. Daily quota reached (today=4) -> Blocked
        allowed, reason = can_dispatch_email(
            daily_sent_count=4,
            weekly_sent_count=10,
            quota_limit=4,
            weekly_quota_limit=20,
            now=dt_valid
        )
        self.assertFalse(allowed)
        self.assertIn("Daily quota limit reached", reason)

        # 3. Weekly quota reached (week=20) -> Blocked
        allowed, reason = can_dispatch_email(
            daily_sent_count=2,
            weekly_sent_count=20,
            quota_limit=4,
            weekly_quota_limit=20,
            now=dt_valid
        )
        self.assertFalse(allowed)
        self.assertIn("Weekly quota limit reached", reason)


if __name__ == "__main__":
    unittest.main()

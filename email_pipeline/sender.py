import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

RESEND_API_URL = "https://api.resend.com/emails"


class UrllibHttpClient:
    """Zero-dependency HTTP client using Python standard library."""
    def post(self, url: str, headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
        req_body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                resp_text = response.read().decode("utf-8")
                return json.loads(resp_text)
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8") if e.fp else str(e)
            raise RuntimeError(f"HTTP Error {e.code}: {err_text}")
        except Exception as e:
            raise RuntimeError(f"Network error: {str(e)}")


def dispatch_outreach_email(
    email_payload: Dict[str, Any],
    dry_run: bool = True,
    api_key: Optional[str] = None,
    http_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Dispatches an outreach email payload to the Resend API or executes in dry-run mode.
    """
    to_addr = email_payload.get("to", ["unknown"])[0]

    # 1. Handle Dry-Run Mode
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "id": f"mock_dry_run_{int(os.times()[4] * 1000)}",
            "email": to_addr,
        }

    # 2. Check API Key
    effective_api_key = api_key or os.environ.get("RESEND_API_KEY")
    if not effective_api_key:
        raise ValueError("Missing RESEND_API_KEY in environment or function arguments")

    # 3. HTTP Dispatch
    client = http_client or UrllibHttpClient()
    headers = {
        "Authorization": f"Bearer {effective_api_key}",
        "Content-Type": "application/json",
        "User-Agent": "CMAA-Outreach-Pipeline/1.0",
    }

    try:
        response_data = client.post(RESEND_API_URL, headers=headers, data=email_payload)
        return {
            "ok": True,
            "dry_run": False,
            "id": response_data.get("id", "sent"),
            "email": to_addr,
        }
    except Exception as err:
        return {
            "ok": False,
            "dry_run": False,
            "error": str(err),
            "email": to_addr,
        }


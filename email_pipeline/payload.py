import re
import os
import html
import base64
from typing import Dict, Any, Optional, List

DEFAULT_FROM_EMAIL = "SUPREMATECHNOLOGIESLTD <suprematechnologiesltd@mail.solitesterror.com>"
DEFAULT_REPLY_TO = "suprematechnologiesltd@solitesterror.com"
OPT_OUT_STATEMENT = "If this message was received in error or you prefer not to receive updates, please disregard this email or reply to let us know."


def build_outreach_email(
    to_email: str,
    developer_name: str,
    app_name: str,
    pain_point: str = "",
    from_email: str = DEFAULT_FROM_EMAIL,
    reply_to: str = DEFAULT_REPLY_TO,
    attachments: Optional[List[Dict[str, str]]] = None,
    attachment_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Builds the official CMAA cold outreach email payload using the approved
    English HTML template with responsive styling and PDF excerpt attachments.
    Properly escapes dynamic external inputs to prevent DOM breakages.
    """
    dev_name_raw = developer_name.strip() if developer_name else "Developer"
    app_name_raw = app_name.strip() if app_name else "Your App"

    # HTML-escaped versions for safe injection into email DOM
    dev_name_clean = html.escape(dev_name_raw)
    app_name_clean = html.escape(app_name_raw)

    subject = f"Mobile Security Assessment Summary: {app_name_raw}"

    # Process attachments
    final_attachments: List[Dict[str, str]] = []
    if attachments:
        for att in attachments:
            if isinstance(att, dict) and "filename" in att and "content" in att:
                final_attachments.append(att)
            elif isinstance(att, str) and os.path.exists(att):
                filename = os.path.basename(att)
                with open(att, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                final_attachments.append({
                    "filename": filename,
                    "content": encoded,
                })

    if attachment_paths:
        for p in attachment_paths:
            if os.path.exists(p):
                filename = os.path.basename(p)
                with open(p, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                final_attachments.append({
                    "filename": filename,
                    "content": encoded,
                })

    # Approved Responsive HTML Template
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CMAA Mobile Security Assessment Summary</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f6f9fc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; color: #2d3748; line-height: 1.6;">
  <table width="100%" border="0" cellpadding="0" cellspacing="0" style="background-color: #f6f9fc; padding: 24px 0;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
          
          <!-- Header -->
          <tr>
            <td style="background-color: #0f172a; padding: 28px 32px; text-align: left;">
              <div style="color: #38bdf8; font-size: 12px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 4px;">CMAA Cloud Security</div>
              <h1 style="color: #ffffff; font-size: 19px; margin: 0; font-weight: 600;">Mobile Security Assessment Summary</h1>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 32px;">
              <p style="font-size: 15px; margin-top: 0;">Hi <b>{dev_name_clean}</b>,</p>
              
              <p style="font-size: 14px; color: #4a5568;">
                We are the <b>CMAA Mobile Security Analysis Team</b> under Suprema Technologies (<a href="https://cmaa.solitesterror.com" style="color: #0284c7; text-decoration: none;">cmaa.solitesterror.com</a>).
              </p>
              
              <p style="font-size: 14px; color: #4a5568;">
                During our recent routine security screening of publicly available mobile applications, our automated engine conducted a non-intrusive static architecture and security baseline scan of your published app, <b>"{app_name_clean}"</b>.
              </p>

              <!-- Attachment Notice Box -->
              <div style="background-color: #f0f9ff; border-left: 4px solid #0284c7; padding: 14px 16px; margin: 20px 0; border-radius: 4px;">
                <p style="margin: 0; font-size: 14px; color: #0369a1;">
                  📎 <b>Attached: Complimentary 2-Page Excerpt Security Report (PDF)</b><br>
                  <span style="font-size: 13px; color: #64748b;">Includes baseline permission configurations, data transmission protection, and compliance indicators for your review.</span>
                </p>
              </div>

              <!-- About Platform -->
              <h3 style="font-size: 15px; color: #0f172a; margin: 24px 0 10px 0; border-bottom: 1px solid #edf2f7; padding-bottom: 6px;">About CMAA Mobile Security Platform</h3>
              <p style="font-size: 13px; color: #64748b; margin-top: 0;">CMAA is a cloud-based automated assessment platform designed for mobile development teams and security professionals:</p>
              
              <ul style="font-size: 13px; color: #4a5568; padding-left: 18px; margin: 0 0 20px 0;">
                <li style="margin-bottom: 6px;"><b>Comprehensive Standard Screening:</b> Covers 79+ mobile security criteria, OWASP Mobile Top 10, and compliance vulnerabilities.</li>
                <li style="margin-bottom: 6px;"><b>Full 36-Page In-Depth Audit:</b> Pinpoints vulnerability locations with severity ratings and clear, actionable source-code remediation guidance.</li>
                <li style="margin-bottom: 6px;"><b>One-Click Cloud Analysis:</b> Supports APK, AAB, and IPA uploads, delivering automated decompilation and audit results within minutes.</li>
              </ul>

              <!-- Pricing Box -->
              <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
                <div style="font-size: 14px; font-weight: 600; color: #0f172a; margin-bottom: 4px;">Platform Pricing:</div>
                <div style="font-size: 13px; color: #475569;">
                  • <b>Full In-Depth Audit:</b> 36-page complete comprehensive report for only <b>$40 USD</b> per scan (no recurring subscription required).
                </div>
              </div>

              <!-- CTA Button -->
              <div style="text-align: center; margin: 28px 0;">
                <a href="https://cmaa.solitesterror.com" target="_blank" style="background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 6px; font-size: 14px; font-weight: 600; display: inline-block;">
                  View Full Report &amp; Platform
                </a>
              </div>

              <p style="font-size: 13px; color: #64748b; margin-bottom: 0;">
                If your team has any questions regarding the findings in the attached report or would like more technical details, feel free to reply directly to this email—our engineering team will be glad to assist you.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; padding: 20px 32px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">
              <p style="margin: 0 0 4px 0; font-weight: 500; color: #64748b;">CMAA Mobile Security Team | Suprema Technologies Ltd.</p>
              <p style="margin: 0 0 8px 0;"><a href="https://cmaa.solitesterror.com" style="color: #0284c7; text-decoration: none;">https://cmaa.solitesterror.com</a></p>
              <p style="margin: 0; font-size: 11px; color: #94a3b8;">
                {OPT_OUT_STATEMENT}
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    # Plain Text Fallback (using raw unescaped strings)
    text_content = f"""Hi {dev_name_raw},

We are the CMAA Mobile Security Analysis Team under Suprema Technologies (https://cmaa.solitesterror.com).

During our recent routine security screening of publicly available mobile applications, our automated engine conducted a non-intrusive static architecture and security baseline scan of your published app, "{app_name_raw}".

To help your team quickly assess the app's current security posture and compliance baseline, we have prepared a complimentary summary and attached a 【2-Page Excerpt Security Report PDF】 to this email (covering baseline permission configurations, data transmission protection, and compliance indicators).

───────────────────────────────────────────────
About CMAA Mobile Security Platform
───────────────────────────────────────────────
CMAA is a cloud-based automated assessment platform designed for mobile development teams and security professionals:
• Comprehensive Standard Screening: Covers 79+ mobile security criteria, OWASP Mobile Top 10, and compliance vulnerabilities.
• Full 36-Page In-Depth Audit: Pinpoints vulnerability locations with severity ratings and clear, actionable source-code remediation guidance.
• One-Click Cloud Analysis: Supports APK, AAB, and IPA uploads, delivering automated decompilation and audit results within minutes.

【Platform Pricing】
• Full In-Depth Audit: Complete 36-page comprehensive security report for only $40 USD per scan (no recurring subscription required).

👉 View Full Report & Platform: https://cmaa.solitesterror.com

If your team has any questions regarding the findings in the attached report or would like more technical details, feel free to reply directly to this email—our engineering team will be glad to assist you.

Wishing you great success with your development!

Best regards,

CMAA Mobile Security Team
Suprema Technologies Ltd.
Website: https://cmaa.solitesterror.com
───────────────────────────────────────────────
{OPT_OUT_STATEMENT}"""

    payload: Dict[str, Any] = {
        "from": from_email,
        "reply_to": reply_to,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
        "text": text_content,
    }

    if final_attachments:
        payload["attachments"] = final_attachments

    return payload

"""
Email Pipeline Package: Hardened Cold Outreach System via Resend.
"""

from .guard import can_dispatch_email, get_random_throttle_delay
from .payload import (
    build_outreach_email,
    DEFAULT_FROM_EMAIL,
    DEFAULT_REPLY_TO,
    OPT_OUT_STATEMENT,
)
from .sender import dispatch_outreach_email

__all__ = [
    "can_dispatch_email",
    "get_random_throttle_delay",
    "build_outreach_email",
    "dispatch_outreach_email",
    "DEFAULT_FROM_EMAIL",
    "DEFAULT_REPLY_TO",
    "OPT_OUT_STATEMENT",
]


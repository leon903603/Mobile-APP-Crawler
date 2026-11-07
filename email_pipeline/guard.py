import random
from datetime import datetime, time
from typing import Tuple


def can_dispatch_email(
    now: datetime,
    daily_sent_count: int,
    weekly_sent_count: int = 0,
    quota_limit: int = 4,
    weekly_quota_limit: int = 20,
    start_hour: int = 9,
    end_hour: int = 18,
    bypass_hours: bool = False,
    allow_weekends: bool = False,
) -> Tuple[bool, str]:
    """
    Evaluates whether an outreach email can be dispatched based on:
    1. Working hour window (default 09:00 - 18:00) unless bypass_hours is True
    2. Weekday constraint (Monday-Friday only) unless allow_weekends or bypass_hours is True
    3. Daily quota limit (default: 4 per day)
    4. Weekly quota limit (default: 20 per calendar week)
    """
    # 1. Check working hours and weekdays
    if not bypass_hours:
        if not allow_weekends and now.weekday() >= 5:
            return False, "Dispatch blocked on weekends (Saturday/Sunday)"

        current_time = now.time()
        work_start = time(start_hour, 0)
        work_end = time(min(23, end_hour), 0)

        if not (work_start <= current_time <= work_end):
            return False, f"Outside working hours ({start_hour:02d}:00-{end_hour:02d}:00)"

    # 2. Check daily quota
    if daily_sent_count >= quota_limit:
        return False, f"Daily quota limit reached ({daily_sent_count}/{quota_limit})"

    # 3. Check weekly quota
    if weekly_sent_count >= weekly_quota_limit:
        return False, f"Weekly quota limit reached ({weekly_sent_count}/{weekly_quota_limit})"

    return True, ""


def get_random_throttle_delay(min_s: int = 180, max_s: int = 420) -> int:
    """
    Returns a randomized sleep delay between min_s and max_s to simulate human behavior
    and prevent triggering ISP spam/rate filters.
    """
    return random.randint(min_s, max_s)

"""Win/loss and realized P&L for a Toss Securities account over any period.

    from tossperf import get_performance

    s = get_performance("2026-01-01", "2026-09-30", env_file=".toss.env")
    s.win_rate, s.wins, s.losses, s.pnl   # pnl is {"KRW": Decimal, "USD": Decimal}
    get_performance(period="ytd").to_dict()
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

from .fetch import FetchError, fetch_orders, load_orders_file
from .matching import RoundTrip, UnmatchedSell, build_round_trips
from .summary import PerformanceSummary, SymbolStats, summarize

__all__ = [
    "get_performance",
    "summarize_orders",
    "resolve_period",
    "fetch_orders",
    "load_orders_file",
    "build_round_trips",
    "summarize",
    "PerformanceSummary",
    "SymbolStats",
    "RoundTrip",
    "UnmatchedSell",
    "FetchError",
]

KST = timezone(timedelta(hours=9))


def resolve_period(period: str, today: date | None = None) -> tuple[date | None, date]:
    """'all', 'ytd', 'mtd', or '<N>d' (last N days including today) → (start, end) in KST."""
    today = today or datetime.now(KST).date()
    period = period.lower()
    if period == "all":
        return None, today
    if period == "ytd":
        return today.replace(month=1, day=1), today
    if period == "mtd":
        return today.replace(day=1), today
    if m := re.fullmatch(r"(\d+)d", period):
        return today - timedelta(days=int(m.group(1)) - 1), today
    raise ValueError(f"unknown period {period!r}; use 'all', 'ytd', 'mtd' or '<N>d'")


def summarize_orders(
    orders: list[dict],
    start: date | str | None = None,
    end: date | str | None = None,
) -> PerformanceSummary:
    """Summarize an order list you already have (API response items or a saved dump)."""
    round_trips, unmatched = build_round_trips(orders)
    return summarize(round_trips, unmatched, start, end)


def get_performance(
    start: date | str | None = None,
    end: date | str | None = None,
    *,
    period: str | None = None,
    account: str | int | None = None,
    skill_dir: str | os.PathLike | None = None,
    env_file: str | os.PathLike | None = None,
    orders: list[dict] | None = None,
) -> PerformanceSummary:
    """Win/loss and realized P&L for round trips closed between start and end (inclusive, KST).

    The full order history is fetched so that sells in the period are matched against
    the buys that opened them (orders after `end` cannot change those matches).
    Pass `orders` to skip the API call.
    Credentials come from the environment (TOSS_API_KEY / TOSS_SECRET_KEY) or `env_file`;
    the account from `account` or TOSS_ACCOUNT.
    """
    if period:
        if start or end:
            raise ValueError("pass either period or start/end, not both")
        start, end = resolve_period(period)

    if orders is None:
        orders = fetch_orders(account, skill_dir=skill_dir, env_file=env_file)
    return summarize_orders(orders, start, end)

"""Win/loss and realized P&L over a period."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from .matching import RoundTrip, UnmatchedSell


@dataclass
class SymbolStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    pnl: Decimal = Decimal(0)
    currency: str = ""

    @property
    def win_rate(self) -> float | None:
        decided = self.wins + self.losses
        return self.wins / decided if decided else None


@dataclass
class PerformanceSummary:
    start: str | None
    end: str | None
    round_trips: list[RoundTrip]
    unmatched_sells: list[UnmatchedSell]
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    pnl: dict[str, Decimal] = field(default_factory=dict)
    per_symbol: dict[str, SymbolStats] = field(default_factory=dict)

    @property
    def trades(self) -> int:
        return len(self.round_trips)

    @property
    def win_rate(self) -> float | None:
        decided = self.wins + self.losses
        return self.wins / decided if decided else None

    def one_line(self) -> str:
        """e.g. '2026-01-01..2026-10-09  54 trades  15W 39L  win 27.8%  P&L KRW +588,986  USD -600.58'"""
        period = f"{self.start or 'start'}..{self.end or 'now'}"
        record = f"{self.wins}W {self.losses}L" + (f" {self.breakeven}BE" if self.breakeven else "")
        rate = f"{self.win_rate:.1%}" if self.win_rate is not None else "-"
        pnl = "  ".join(f"{cur} {amount:+,}" for cur, amount in sorted(self.pnl.items())) or "-"
        noun = "trade" if self.trades == 1 else "trades"
        return f"{period}  {self.trades} {noun}  {record}  win {rate}  P&L {pnl}"

    def to_dict(self) -> dict:
        """JSON-friendly view; money stays exact as strings."""
        return {
            "period": {"start": self.start, "end": self.end},
            "round_trips": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "breakeven": self.breakeven,
            "win_rate": self.win_rate,
            "pnl": {cur: str(amount) for cur, amount in self.pnl.items()},
            "unmatched_sells": [
                {"symbol": u.symbol, "quantity": str(u.quantity), "order_id": u.order_id} for u in self.unmatched_sells
            ],
            "per_symbol": {
                sym: {
                    "trades": s.trades,
                    "wins": s.wins,
                    "losses": s.losses,
                    "win_rate": s.win_rate,
                    "pnl": str(s.pnl),
                    "currency": s.currency,
                }
                for sym, s in sorted(self.per_symbol.items(), key=lambda kv: -kv[1].trades)
            },
        }


def _settle(amount: Decimal, currency: str) -> Decimal:
    return amount.quantize(Decimal(1) if currency == "KRW" else Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _iso(d: date | str | None) -> str | None:
    return d.isoformat() if isinstance(d, date) else d


def summarize(
    round_trips: list[RoundTrip],
    unmatched: list[UnmatchedSell] = (),
    start: date | str | None = None,
    end: date | str | None = None,
) -> PerformanceSummary:
    """Keep round trips *closed* within [start, end] (inclusive, KST dates) and tally them."""
    start, end = _iso(start), _iso(end)

    def in_period(day: str) -> bool:
        return (start is None or day >= start) and (end is None or day <= end)

    trips = [t for t in round_trips if in_period(t.closed_date)]
    summary = PerformanceSummary(
        start=start,
        end=end,
        round_trips=trips,
        unmatched_sells=[u for u in unmatched if in_period(u.closed_at[:10])],
    )

    pnl: dict[str, Decimal] = defaultdict(Decimal)
    per_symbol: dict[str, SymbolStats] = defaultdict(SymbolStats)
    for t in trips:
        stats = per_symbol[t.symbol]
        stats.trades += 1
        stats.pnl += t.pnl
        stats.currency = t.currency
        pnl[t.currency] += t.pnl
        if t.pnl > 0:
            summary.wins += 1
            stats.wins += 1
        elif t.pnl < 0:
            summary.losses += 1
            stats.losses += 1
        else:
            summary.breakeven += 1

    # Per-share fee splits leave long repeating decimals; totals are settled amounts.
    summary.pnl = {cur: _settle(amount, cur) for cur, amount in pnl.items()}
    for stats in per_symbol.values():
        stats.pnl = _settle(stats.pnl, stats.currency)
    summary.per_symbol = dict(per_symbol)
    return summary

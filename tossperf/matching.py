"""FIFO matching of filled SELLs against BUYs into round trips."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal


def dec(value) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal(0)


@dataclass(frozen=True)
class RoundTrip:
    symbol: str
    currency: str
    quantity: Decimal
    buy_price: Decimal
    sell_price: Decimal
    pnl: Decimal  # net of commission and tax on both legs
    opened_at: str
    closed_at: str

    @property
    def closed_date(self) -> str:
        """KST date (YYYY-MM-DD) the position was closed; timestamps carry a +09:00 offset."""
        return self.closed_at[:10]


@dataclass(frozen=True)
class UnmatchedSell:
    symbol: str
    quantity: Decimal
    order_id: str
    closed_at: str


def build_round_trips(orders: list[dict]) -> tuple[list[RoundTrip], list[UnmatchedSell]]:
    filled = [o for o in orders if dec((o.get("execution") or {}).get("filledQuantity")) > 0]
    filled.sort(key=lambda o: o["execution"].get("filledAt") or o["orderedAt"])

    lots: dict[str, deque] = defaultdict(deque)
    round_trips: list[RoundTrip] = []
    unmatched: list[UnmatchedSell] = []

    for order in filled:
        ex = order["execution"]
        symbol = order["symbol"]
        qty = dec(ex["filledQuantity"])
        price = dec(ex.get("averageFilledPrice"))
        filled_at = ex.get("filledAt") or order["orderedAt"]
        # Fees are for the whole fill; carry them per-share so partial
        # consumption of a lot attributes them proportionally.
        fee_per_share = (dec(ex.get("commission")) + dec(ex.get("tax"))) / qty

        if order["side"] == "BUY":
            lots[symbol].append({"qty": qty, "price": price, "fee": fee_per_share, "at": filled_at})
            continue

        remaining = qty
        while remaining > 0 and lots[symbol]:
            lot = lots[symbol][0]
            take = min(remaining, lot["qty"])
            cost = take * (lot["price"] + lot["fee"])
            proceeds = take * (price - fee_per_share)
            round_trips.append(
                RoundTrip(
                    symbol=symbol,
                    currency=order["currency"],
                    quantity=take,
                    buy_price=lot["price"],
                    sell_price=price,
                    pnl=proceeds - cost,
                    opened_at=lot["at"],
                    closed_at=filled_at,
                )
            )
            lot["qty"] -= take
            remaining -= take
            if lot["qty"] == 0:
                lots[symbol].popleft()

        if remaining > 0:
            unmatched.append(UnmatchedSell(symbol, remaining, order["orderId"], filled_at))

    return round_trips, unmatched

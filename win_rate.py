#!/usr/bin/env python3
"""Compute trading win-rate from Toss Securities closed order history.

Fetches filled orders via the tossinvest-skill CLI, matches SELLs against
BUYs FIFO per symbol, and reports the share of round trips that were
profitable net of commission and tax.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def resolve_skill_dir(explicit: str | None) -> Path:
    if explicit:
        # An explicit path that doesn't work is a typo, not a reason to search elsewhere.
        if (Path(explicit) / "scripts/tossinvest.py").is_file():
            return Path(explicit).resolve()
        sys.exit(f"--skill-dir {explicit} has no scripts/tossinvest.py")

    candidates = [
        os.environ.get("TOSSINVEST_SKILL_DIR"),
        HERE.parent / ".claude/skills/tossinvest-skill",
        HERE / "tossinvest-skill",
        HERE.parent / "tossinvest-skill",
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "scripts/tossinvest.py").is_file():
            return Path(candidate).resolve()
    sys.exit(
        "Could not find the tossinvest-skill directory. Pass --skill-dir /path/to/tossinvest-skill "
        "(the directory containing scripts/tossinvest.py)."
    )


def dec(value) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal(0)


def fetch_orders(skill_dir: Path, account: str | None, from_date: str | None, to_date: str | None) -> list[dict]:
    cli = skill_dir / "scripts/tossinvest.py"
    orders: list[dict] = []
    cursor: str | None = None

    while True:
        cmd = [sys.executable, str(cli), "orders", "--status", "CLOSED", "--limit", "100"]
        for flag, value in (
            ("--account", account),
            ("--from-date", from_date),
            ("--to-date", to_date),
            ("--cursor", cursor),
        ):
            if value:
                cmd += [flag, value]

        proc = subprocess.run(cmd, cwd=skill_dir, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.exit(f"order fetch failed: {proc.stderr.strip() or proc.stdout.strip()}")

        payload = json.loads(proc.stdout)
        page = payload.get("result", payload)
        orders += page.get("orders", [])
        cursor = page.get("nextCursor")
        if not page.get("hasNext") or not cursor:
            return orders


def build_round_trips(orders: list[dict]) -> tuple[list[dict], list[dict]]:
    """FIFO-match SELLs against BUYs. Returns (round_trips, unmatched_sells)."""
    filled = [o for o in orders if dec(o.get("execution", {}).get("filledQuantity")) > 0]
    filled.sort(key=lambda o: o["execution"].get("filledAt") or o["orderedAt"])

    lots: dict[str, deque] = defaultdict(deque)
    round_trips: list[dict] = []
    unmatched: list[dict] = []

    for order in filled:
        ex = order["execution"]
        symbol = order["symbol"]
        qty = dec(ex["filledQuantity"])
        price = dec(ex.get("averageFilledPrice"))
        # Fees are for the whole fill; carry them per-share so partial
        # consumption of a lot attributes them proportionally.
        fee_per_share = (dec(ex.get("commission")) + dec(ex.get("tax"))) / qty

        if order["side"] == "BUY":
            lots[symbol].append({"qty": qty, "price": price, "fee": fee_per_share})
            continue

        remaining = qty
        while remaining > 0 and lots[symbol]:
            lot = lots[symbol][0]
            take = min(remaining, lot["qty"])
            cost = take * (lot["price"] + lot["fee"])
            proceeds = take * (price - fee_per_share)
            round_trips.append(
                {
                    "symbol": symbol,
                    "currency": order["currency"],
                    "quantity": take,
                    "buy_price": lot["price"],
                    "sell_price": price,
                    "pnl": proceeds - cost,
                    "closed_at": ex.get("filledAt") or order["orderedAt"],
                }
            )
            lot["qty"] -= take
            remaining -= take
            if lot["qty"] == 0:
                lots[symbol].popleft()

        if remaining > 0:
            unmatched.append({"symbol": symbol, "quantity": str(remaining), "order_id": order["orderId"]})

    return round_trips, unmatched


def report(round_trips: list[dict], unmatched: list[dict]) -> dict:
    wins = [t for t in round_trips if t["pnl"] > 0]
    losses = [t for t in round_trips if t["pnl"] < 0]
    scratches = [t for t in round_trips if t["pnl"] == 0]
    decided = len(wins) + len(losses)

    pnl_by_currency: dict[str, Decimal] = defaultdict(Decimal)
    for trade in round_trips:
        pnl_by_currency[trade["currency"]] += trade["pnl"]

    per_symbol: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0})
    for trade in round_trips:
        entry = per_symbol[trade["symbol"]]
        entry["trades"] += 1
        entry["wins"] += 1 if trade["pnl"] > 0 else 0

    return {
        "round_trips": len(round_trips),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(scratches),
        "win_rate": float(len(wins) / decided) if decided else None,
        "net_pnl": {cur: str(amount) for cur, amount in pnl_by_currency.items()},
        "unmatched_sells": unmatched,
        "per_symbol": {
            sym: {**stats, "win_rate": stats["wins"] / stats["trades"]}
            for sym, stats in sorted(per_symbol.items(), key=lambda kv: -kv[1]["trades"])
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", help="Toss accountSeq (defaults to TOSS_ACCOUNT env var)")
    parser.add_argument("--from-date", help="Start date, YYYY-MM-DD (KST)")
    parser.add_argument("--to-date", help="End date, YYYY-MM-DD (KST)")
    parser.add_argument("--orders-file", help="Read a saved orders JSON dump instead of calling the API")
    parser.add_argument("--save-orders", help="Write the fetched raw orders to this path")
    parser.add_argument("--skill-dir", help="Path to the tossinvest-skill directory")
    args = parser.parse_args()

    if args.orders_file:
        raw = json.loads(Path(args.orders_file).read_text())
        orders = raw if isinstance(raw, list) else raw.get("result", raw).get("orders", [])
    else:
        orders = fetch_orders(resolve_skill_dir(args.skill_dir), args.account, args.from_date, args.to_date)
        if args.save_orders:
            Path(args.save_orders).write_text(json.dumps(orders, indent=2, ensure_ascii=False))

    round_trips, unmatched = build_round_trips(orders)
    summary = report(round_trips, unmatched)
    summary["orders_examined"] = len(orders)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
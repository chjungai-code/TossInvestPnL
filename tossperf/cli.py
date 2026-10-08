"""Command line: tossperf [--from-date D] [--to-date D | --period ytd] ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import FetchError, get_performance, load_orders_file
from .fetch import fetch_orders


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tossperf", description="Win/loss and realized P&L from Toss Securities order history."
    )
    parser.add_argument("--account", help="Toss accountSeq (defaults to TOSS_ACCOUNT env var)")
    parser.add_argument("--from-date", help="Count round trips closed on/after this date, YYYY-MM-DD (KST)")
    parser.add_argument("--to-date", help="Count round trips closed on/before this date, YYYY-MM-DD (KST)")
    parser.add_argument("--period", help="Shortcut instead of dates: all, ytd, mtd, or <N>d (e.g. 30d)")
    parser.add_argument("--orders-file", help="Read a saved orders JSON dump instead of calling the API")
    parser.add_argument("--save-orders", help="Write the fetched raw orders to this path")
    parser.add_argument("--skill-dir", help="Path to the tossinvest-skill directory")
    parser.add_argument("--env-file", help="KEY=VALUE file with TOSS_API_KEY/TOSS_SECRET_KEY (e.g. .toss.env)")
    parser.add_argument("--trades", action="store_true", help="Include each round trip in the output")
    args = parser.parse_args(argv)

    try:
        if args.orders_file:
            orders = load_orders_file(args.orders_file)
        else:
            orders = fetch_orders(args.account, skill_dir=args.skill_dir, env_file=args.env_file)
            if args.save_orders:
                Path(args.save_orders).write_text(json.dumps(orders, indent=2, ensure_ascii=False))
        summary = get_performance(args.from_date, args.to_date, period=args.period, orders=orders)
    except (FetchError, ValueError) as exc:
        sys.exit(str(exc))

    out = summary.to_dict()
    out["orders_examined"] = len(orders)
    if args.trades:
        out["trades"] = [
            {
                "symbol": t.symbol,
                "quantity": str(t.quantity),
                "buy_price": str(t.buy_price),
                "sell_price": str(t.sell_price),
                "pnl": str(t.pnl),
                "currency": t.currency,
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
            }
            for t in summary.round_trips
        ]
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

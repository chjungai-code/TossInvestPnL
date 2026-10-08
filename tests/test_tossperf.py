from datetime import date
from decimal import Decimal
import unittest

from tossperf import get_performance, resolve_period, summarize_orders


def order(side, symbol, qty, price, filled_at, commission="0", tax="0", currency="KRW", oid=None):
    return {
        "orderId": oid or f"{side}-{symbol}-{filled_at}",
        "symbol": symbol,
        "side": side,
        "status": "FILLED",
        "currency": currency,
        "orderedAt": filled_at,
        "execution": {
            "filledQuantity": str(qty),
            "averageFilledPrice": str(price),
            "commission": commission,
            "tax": tax,
            "filledAt": filled_at,
        },
    }


class PerformanceTests(unittest.TestCase):
    def test_fifo_with_fees(self):
        orders = [
            order("BUY", "A", 2, 100, "2026-01-02T10:00:00+09:00", commission="2"),
            order("BUY", "A", 1, 130, "2026-01-03T10:00:00+09:00"),
            order("SELL", "A", 3, 120, "2026-01-04T10:00:00+09:00", tax="3"),
        ]
        s = summarize_orders(orders)
        self.assertEqual((s.trades, s.wins, s.losses), (2, 1, 1))
        # lot 1: 2*(120-1) - 2*(100+1) = 36; lot 2: 1*(120-1) - 130 = -11
        self.assertEqual(s.pnl, {"KRW": Decimal(25)})

    def test_period_counts_by_close_date_and_uses_earlier_buys(self):
        orders = [
            order("BUY", "A", 1, 100, "2025-12-15T10:00:00+09:00"),
            order("SELL", "A", 1, 150, "2026-01-10T10:00:00+09:00"),
            order("BUY", "B", 1, 50, "2026-01-05T10:00:00+09:00"),
            order("SELL", "B", 1, 40, "2026-02-10T10:00:00+09:00"),
        ]
        jan = get_performance("2026-01-01", date(2026, 1, 31), orders=orders)
        self.assertEqual((jan.trades, jan.wins, jan.losses), (1, 1, 0))
        self.assertEqual(jan.pnl, {"KRW": Decimal(50)})
        self.assertEqual(jan.unmatched_sells, [])

    def test_currencies_kept_separate_and_partial_cancels_count(self):
        canceled = order("SELL", "AAPL", 1, 210, "2026-03-02T23:00:00+09:00", currency="USD")
        canceled["status"] = "CANCELED"  # partially filled before cancel
        orders = [
            order("BUY", "AAPL", 2, 200, "2026-03-01T23:00:00+09:00", currency="USD"),
            canceled,
            order("BUY", "005930", 1, 70000, "2026-03-03T10:00:00+09:00"),
            order("SELL", "005930", 1, 69000, "2026-03-04T10:00:00+09:00"),
        ]
        s = summarize_orders(orders)
        self.assertEqual(s.pnl, {"USD": Decimal(10), "KRW": Decimal(-1000)})
        self.assertEqual(s.per_symbol["AAPL"].win_rate, 1.0)
        self.assertEqual(s.win_rate, 0.5)

    def test_unmatched_sell_reported(self):
        s = summarize_orders([order("SELL", "A", 1, 10, "2026-01-01T10:00:00+09:00")])
        self.assertEqual(s.trades, 0)
        self.assertIsNone(s.win_rate)
        self.assertEqual(s.unmatched_sells[0].quantity, Decimal(1))

    def test_one_line(self):
        orders = [
            order("BUY", "A", 1, 1000, "2026-01-02T10:00:00+09:00"),
            order("SELL", "A", 1, 2500, "2026-01-03T10:00:00+09:00"),
        ]
        self.assertEqual(
            get_performance("2026-01-01", "2026-01-31", orders=orders).one_line(),
            "2026-01-01..2026-01-31  1 trade  1W 0L  win 100.0%  P&L KRW +1,500",
        )
        self.assertEqual(
            get_performance("2026-02-01", "2026-02-28", orders=orders).one_line(),
            "2026-02-01..2026-02-28  0 trades  0W 0L  win -  P&L -",
        )

    def test_resolve_period(self):
        today = date(2026, 10, 9)
        self.assertEqual(resolve_period("ytd", today), (date(2026, 1, 1), today))
        self.assertEqual(resolve_period("mtd", today), (date(2026, 10, 1), today))
        self.assertEqual(resolve_period("30d", today), (date(2026, 9, 10), today))
        self.assertEqual(resolve_period("all", today), (None, today))
        with self.assertRaises(ValueError):
            resolve_period("1y", today)

    def test_period_and_dates_are_exclusive(self):
        with self.assertRaises(ValueError):
            get_performance("2026-01-01", period="ytd", orders=[])


if __name__ == "__main__":
    unittest.main()

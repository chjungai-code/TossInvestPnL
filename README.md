# tossperf

Win/loss and realized P&L for a Toss Securities account over any period. Filled SELLs are matched
FIFO against BUYs per symbol; P&L is net of commission and tax and kept per currency (KRW, USD).
A trade counts toward the period in which it was **closed**, and buys from before the period are
still used to match sells inside it.

## Setup

```bash
pip install -e /path/to/this/repo   # or put the repo on PYTHONPATH
```

It calls the API through [tossinvest-skill](https://github.com/BEOKS/tossinvest-skill)'s CLI, found via
`skill_dir=`, `TOSSINVEST_SKILL_DIR`, `./tossinvest-skill`, this repo's `tossinvest-skill/`, or
`~/.claude/skills/tossinvest-skill`. Credentials come from `TOSS_API_KEY` / `TOSS_SECRET_KEY` in the
environment or an `env_file`; the account from `account=` or `TOSS_ACCOUNT`.

## Python

```python
from tossperf import get_performance

s = get_performance("2026-07-01", "2026-09-30", account=1, env_file=".toss.env")
s.wins, s.losses, s.win_rate      # 2, 1, 0.667
s.pnl                             # {"KRW": Decimal("64499"), "USD": Decimal("-92.27")}
s.per_symbol["005930"].win_rate
s.round_trips                     # list[RoundTrip] with prices, quantity, pnl, open/close times

get_performance(period="ytd")     # also "mtd", "all", "30d", "90d", ...
get_performance(period="30d").to_dict()   # JSON-friendly
```

To query several periods without refetching, fetch once and pass `orders=`:

```python
from tossperf import fetch_orders, get_performance

orders = fetch_orders(account=1, env_file=".toss.env")
q3 = get_performance("2026-07-01", "2026-09-30", orders=orders)
ytd = get_performance(period="ytd", orders=orders)
```

## CLI

```bash
tossperf --period ytd --env-file .toss.env
tossperf --from-date 2026-07-01 --to-date 2026-09-30 --trades
tossperf --orders-file orders.json          # offline, from a saved dump
python -m tossperf ...                      # same, without installing
```

`win_rate.py` remains as a compatibility wrapper around the CLI.

## Tests

```bash
python -m unittest discover -s tests -t .
```

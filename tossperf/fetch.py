"""Fetch closed orders from Toss Securities via the tossinvest-skill CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FetchError(RuntimeError):
    pass


def resolve_skill_dir(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        # An explicit path that doesn't work is a typo, not a reason to search elsewhere.
        if (Path(explicit) / "scripts/tossinvest.py").is_file():
            return Path(explicit).resolve()
        raise FetchError(f"skill_dir {explicit} has no scripts/tossinvest.py")

    candidates = [
        os.environ.get("TOSSINVEST_SKILL_DIR"),
        Path.cwd() / "tossinvest-skill",
        PROJECT_ROOT / "tossinvest-skill",
        Path.home() / ".claude/skills/tossinvest-skill",
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "scripts/tossinvest.py").is_file():
            return Path(candidate).resolve()
    raise FetchError(
        "Could not find the tossinvest-skill directory. Pass skill_dir=... or set TOSSINVEST_SKILL_DIR "
        "(the directory containing scripts/tossinvest.py)."
    )


def load_env_file(path: str | os.PathLike) -> dict[str, str]:
    """Parse simple KEY=VALUE lines (e.g. .toss.env). Values are never logged."""
    env: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        env[key.strip()] = value.strip().strip("'\"")
    return env


def fetch_orders(
    account: str | int | None = None,
    from_date: date | str | None = None,
    to_date: date | str | None = None,
    *,
    skill_dir: str | os.PathLike | None = None,
    env_file: str | os.PathLike | None = None,
) -> list[dict]:
    """Return every CLOSED order placed between from_date and to_date (inclusive, KST).

    Note: the API returns only a short recent window when `to` is sent without `from`,
    so a lone to_date is paired with an early from_date here.
    """
    if to_date and not from_date:
        from_date = "2000-01-01"
    cli = resolve_skill_dir(skill_dir) / "scripts/tossinvest.py"
    env = dict(os.environ)
    if env_file:
        env.update(load_env_file(env_file))

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
                cmd += [flag, str(value)]

        proc = subprocess.run(cmd, cwd=cli.parent.parent, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise FetchError(f"order fetch failed: {proc.stderr.strip() or proc.stdout.strip()}")

        payload = json.loads(proc.stdout)
        page = payload.get("result", payload)
        orders += page.get("orders", [])
        cursor = page.get("nextCursor")
        if not page.get("hasNext") or not cursor:
            return orders


def load_orders_file(path: str | os.PathLike) -> list[dict]:
    """Read a saved dump: either a bare list or a raw API response envelope."""
    raw = json.loads(Path(path).read_text())
    return raw if isinstance(raw, list) else raw.get("result", raw).get("orders", [])

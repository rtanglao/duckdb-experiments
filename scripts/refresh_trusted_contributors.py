#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Refresh the committed trusted-contributor lists from thunderbird-metrics-and-reports.

    uv run scripts/refresh_trusted_contributors.py
    uv run scripts/refresh_trusted_contributors.py --dry-run

The lists are small (30 and 4 lines) and change rarely, so they are committed
here rather than fetched at query time -- an analysis run should not depend on
the network, and a query's result should be reproducible from the repo alone.
sql/trusted_contributors.sql reads the files this script writes.
"""

import argparse
import sys
from pathlib import Path

import httpx

RAW = ("https://raw.githubusercontent.com/thunderbird/"
       "thunderbird-metrics-and-reports/main/CONCATENATED_FILES")

LISTS = {
    "desktop": f"{RAW}/DESKTOP/thunderbird-desktop-trusted-contributors.csv",
    "android": f"{RAW}/ANDROID/thunderbird-android-trusted-contributors.csv",
}

DEST = Path(__file__).resolve().parent.parent / "data" / "trusted-contributors"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    changed = 0

    for product, url in LISTS.items():
        path = DEST / f"thunderbird-{product}-trusted-contributors.csv"
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"{product}: FAILED -- {exc}", file=sys.stderr)
            return 1

        new = resp.text
        old = path.read_text() if path.exists() else None

        if old == new:
            print(f"{product}: unchanged ({len(new.splitlines()) - 1} names)")
            continue

        changed += 1
        old_names = _names(old)
        new_names = _names(new)
        for name in sorted(new_names - old_names):
            print(f"{product}: + {name}")
        for name in sorted(old_names - new_names):
            print(f"{product}: - {name}")
        if not (new_names ^ old_names):
            print(f"{product}: counts changed, membership identical")

        if args.dry_run:
            print(f"{product}: (dry run, not written)")
        else:
            path.write_text(new)
            print(f"{product}: wrote {path.relative_to(DEST.parent.parent)}")

    if changed and not args.dry_run:
        print("\nMembership changed -- rerun the trusted views:\n"
              "  duckdb thunderbird.duckdb -f sql/trusted_contributors.sql")
    return 0


def _names(text: str | None) -> set[str]:
    """Creator column of a `creator,count` CSV, header dropped."""
    if not text:
        return set()
    return {line.split(",")[0] for line in text.splitlines()[1:] if line.strip()}


if __name__ == "__main__":
    sys.exit(main())

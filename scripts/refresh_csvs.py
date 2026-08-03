#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Refresh the year directories from the aaq-scraper repo.

aaq-scraper is where the scraped CSVs actually live and are version-controlled.
The copies here are derived data and are gitignored.

    uv run scripts/refresh_csvs.py              # pull aaq-scraper, then mirror
    uv run scripts/refresh_csvs.py --dry-run    # show what would change
    uv run scripts/refresh_csvs.py --no-pull    # mirror what is checked out
    uv run scripts/refresh_csvs.py --rebuild    # also rebuild thunderbird.duckdb

The scraper location defaults to a sibling checkout; override with --scraper or
the AAQ_SCRAPER environment variable.

Year directories are discovered, not hardcoded, so 2027 works with no edit.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCRAPER = ROOT.parent / "aaq-scraper"
SCRAPER_URL = "https://github.com/thunderbird/aaq-scraper.git"
YEAR = re.compile(r"^\d{4}$")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, **kw)


def git_pull(scraper: Path) -> None:
    print(f"==> pulling {scraper}")
    # --ff-only so a dirty or diverged scraper checkout fails loudly rather
    # than silently merging.
    run(["git", "-C", str(scraper), "pull", "--ff-only"])


def head(scraper: Path) -> str:
    out = run(["git", "-C", str(scraper), "log", "-1", "--format=%h %s"],
              capture_output=True)
    return out.stdout.strip()


def same(src: Path, dst: Path) -> bool:
    """rsync's quick check: skip when size and mtime both match."""
    if not dst.exists():
        return False
    a, b = src.stat(), dst.stat()
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def mirror(src_dir: Path, dst_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Copy changed files and delete extras. Returns (copied, deleted)."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    src_names = {p.name for p in src_dir.iterdir() if p.is_file()}

    copied = 0
    for name in sorted(src_names):
        src, dst = src_dir / name, dst_dir / name
        if same(src, dst):
            continue
        if not dry_run:
            shutil.copy2(src, dst)  # copy2 preserves mtime, so reruns are quiet
        copied += 1

    deleted = 0
    for dst in sorted(dst_dir.iterdir()):
        if dst.is_file() and dst.name not in src_names:
            if not dry_run:
                dst.unlink()
            deleted += 1

    return copied, deleted


def db_is_locked(db: Path) -> bool:
    if not db.exists():
        return False
    probe = subprocess.run(
        ["duckdb", "-readonly", str(db), "-c", "SELECT 1"],
        capture_output=True, text=True,
    )
    return probe.returncode != 0


def rebuild(root: Path) -> None:
    db = root / "thunderbird.duckdb"
    print("==> rebuilding thunderbird.duckdb")
    if db_is_locked(db):
        sys.exit("error: thunderbird.duckdb is locked -- close the DuckDB UI first")
    run(["duckdb", str(db), "-f", "sql/build_desktop_db.sql"], cwd=root)

    print("==> refreshing output/parquet/")
    (root / "output" / "parquet").mkdir(parents=True, exist_ok=True)
    run(["duckdb", "-readonly", str(db), "-c",
         "COPY questions TO 'output/parquet/questions.parquet' "
         "(FORMAT parquet, COMPRESSION zstd);"
         "COPY answers TO 'output/parquet/answers.parquet' "
         "(FORMAT parquet, COMPRESSION zstd);"], cwd=root)
    print("    remember to commit output/parquet/ if the snapshot moved")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scraper", type=Path,
                    default=Path(os.environ.get("AAQ_SCRAPER", DEFAULT_SCRAPER)),
                    help="path to the aaq-scraper checkout")
    ap.add_argument("--no-pull", action="store_true",
                    help="mirror what is already checked out")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild thunderbird.duckdb and the Parquet snapshot")
    args = ap.parse_args()

    scraper = args.scraper.expanduser().resolve()
    if not (scraper / ".git").is_dir():
        sys.exit(
            f"error: no aaq-scraper checkout at {scraper}\n\n"
            "Clone it next to this repo, or point --scraper at an existing one:\n\n"
            f"    git clone {SCRAPER_URL} {scraper}\n"
            f"    uv run scripts/refresh_csvs.py --scraper /path/to/aaq-scraper"
        )

    if not args.no_pull:
        git_pull(scraper)
    print(f"    at {head(scraper)}")

    years = sorted(p for p in scraper.iterdir() if p.is_dir() and YEAR.match(p.name))
    if not years:
        sys.exit(f"error: no year directories found in {scraper}")

    print(f"==> mirroring {len(years)} year(s): {' '.join(p.name for p in years)}")
    total_copied = total_deleted = 0
    for src_dir in years:
        dst_dir = ROOT / src_dir.name
        copied, deleted = mirror(src_dir, dst_dir, args.dry_run)
        total_copied += copied
        total_deleted += deleted
        present = sum(1 for p in dst_dir.iterdir() if p.is_file())
        print(f"    {src_dir.name}  {copied:5d} copied  {deleted:3d} deleted"
              f"  ({present} files present)")

    verb = "would change" if args.dry_run else "changed"
    print(f"==> {total_copied} copied, {total_deleted} deleted {verb}")
    if args.dry_run:
        return

    if args.rebuild:
        rebuild(ROOT)


if __name__ == "__main__":
    main()

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Plot antivirus mentions in Thunderbird desktop support threads, by quarter.

Runs sql/antivirus_mentions.sql, then draws output/antivirus_quarterly.png:
an overall trend strip on top, and small multiples for the top 10 vendors
below on a shared scale.

    uv run sql/plot_antivirus.py
    uv run sql/plot_antivirus.py --trusted

--trusted runs sql/antivirus_mentions_trusted.sql instead, which counts only
answers from a trusted contributor or the person who asked, and writes the
_trusted twins of both the CSV and the PNG.

Ten series can't be ten colors -- the categorical palette caps at eight, and
all-pairs forms cap at three. Small multiples carry identity in the panel
title instead, so every panel uses the same single hue.

Requires the database to be free of locks -- close the DuckDB UI first.
"""

import collections
import csv
import subprocess
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output"
TRUSTED = "--trusted" in sys.argv
SUFFIX = "_trusted" if TRUSTED else ""
SQL_IN = f"antivirus_mentions{SUFFIX}.sql"
CSV_IN = OUT_DIR / f"antivirus_quarterly{SUFFIX}.csv"
PNG_OUT = OUT_DIR / f"antivirus_quarterly{SUFFIX}.png"

# Reference palette, light mode -- single categorical slot, validated.
SURFACE = "#fcfcfb"
SERIES = "#2a78d6"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"


def load():
    OUT_DIR.mkdir(exist_ok=True)
    subprocess.run(
        ["duckdb", "-readonly", str(ROOT / "thunderbird.duckdb"),
         "-f", str(ROOT / "sql" / SQL_IN)],
        check=True, cwd=ROOT, stdout=subprocess.DEVNULL,
    )
    series = collections.defaultdict(dict)
    for r in csv.DictReader(CSV_IN.open()):
        series[r["series"]][date.fromisoformat(r["period"])] = int(r["threads"])

    # Drop the trailing partial quarter.
    today = date.today()
    current = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    periods = sorted(p for p in series["_all_threads"] if p < current)
    return series, periods


def style(ax, periods):
    ax.set_facecolor(SURFACE)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=9, length=0)
    ax.set_xlim(periods[0], periods[-1])


def main():
    series, periods = load()
    vendors = sorted(
        (s for s in series if not s.startswith("_")),
        key=lambda s: -sum(series[s].get(p, 0) for p in periods),
    )
    vmax = max(series[v].get(p, 0) for v in vendors for p in periods)

    plt.rcParams["font.family"] = [
        "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans",
    ]
    fig = plt.figure(figsize=(11.5, 9.4), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(
        3, 5, height_ratios=[1.6, 1, 1],
        left=0.06, right=0.975, top=0.845, bottom=0.10, hspace=0.85, wspace=0.28,
    )

    av = [series["_all_antivirus"].get(p, 0) for p in periods]
    total = [series["_all_threads"].get(p, 0) for p in periods]
    share = 100 * sum(av) / sum(total)

    fig.text(0.06, 0.968,
             "Antivirus comes up in 1 of every 13 Thunderbird desktop threads",
             color=INK_PRIMARY, fontsize=18, fontweight="bold", va="top")
    fig.text(0.06, 0.925,
             f"{sum(av):,} of {sum(total):,} threads ({share:.1f}%) mention "
             "antivirus. Quarterly, 2023 Q1 – 2026 Q2. A thread is a question "
             "plus all its answers.",
             color=INK_SECONDARY, fontsize=10.5, va="top")

    # --- Overall strip ---------------------------------------------------
    ax = fig.add_subplot(gs[0, :])
    style(ax, periods)
    ax.plot(periods, av, color=SERIES, linewidth=2, solid_capstyle="round")
    ax.set_ylim(0, max(av) * 1.18)
    ax.set_title("Threads mentioning antivirus, anti-virus, or anti virus"
                 + (" (trusted answers only)" if TRUSTED else ""),
                 color=INK_SECONDARY, fontsize=11.5, fontweight="bold",
                 loc="left", pad=10)
    ax.yaxis.set_major_locator(MultipleLocator(100))
    ax.set_xticks([date(y, 1, 1) for y in (2023, 2024, 2025, 2026)],
                  ["2023", "2024", "2025", "2026"])
    peak = max(range(len(av)), key=lambda i: av[i])
    for i, ha in ((peak, "center"), (len(av) - 1, "right")):
        ax.annotate(f"{av[i]}", (periods[i], av[i]), textcoords="offset points",
                    xytext=(0, 9), ha=ha, color=INK_PRIMARY, fontsize=10,
                    fontweight="bold")
        ax.plot([periods[i]], [av[i]], "o", color=SERIES, markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=2)

    # --- Vendor small multiples ------------------------------------------
    first_panel = None
    for n, name in enumerate(vendors):
        ax = fig.add_subplot(gs[1 + n // 5, n % 5])
        first_panel = first_panel or ax
        values = [series[name].get(p, 0) for p in periods]
        style(ax, periods)
        ax.plot(periods, values, color=SERIES, linewidth=1.8,
                solid_capstyle="round")
        ax.fill_between(periods, values, color=SERIES, alpha=0.10, linewidth=0)
        ax.set_ylim(0, vmax + 10)
        ax.yaxis.set_major_locator(MultipleLocator(50))
        ax.set_title(f"{name}\n{sum(values):,} threads", color=INK_PRIMARY,
                     fontsize=10, fontweight="bold", loc="left", pad=8,
                     linespacing=1.5)
        ax.set_xticks([date(y, 1, 1) for y in (2023, 2025)])
        ax.set_xticklabels(["’23", "’25"])
        if n % 5:
            ax.set_yticklabels([])

    # Section header, anchored above the first panel rather than at a guessed
    # figure coordinate -- otherwise it lands on the strip's x-axis labels.
    fig.text(0.06, first_panel.get_position().y1 + 0.058,
             "Top 10 vendors by threads mentioning them — every panel on the "
             f"same 0–{vmax + 10} scale",
             color=INK_SECONDARY, fontsize=11.5, fontweight="bold", va="bottom")

    fig.text(0.06, 0.032,
             "Source: support.mozilla.org daily scrapes, product=thunderbird, "
             "2023-01-01 to 2026-06-30. Word-boundary matches on lowercased HTML.\n"
             "Norton includes Symantec, ESET includes NOD32, Microsoft Defender "
             "includes Windows Security. Bare “AV” excluded as ambiguous.",
             color=INK_MUTED, fontsize=8.5, va="bottom", linespacing=1.6)

    fig.savefig(PNG_OUT, dpi=200, facecolor=SURFACE)
    print(f"wrote {PNG_OUT}")


if __name__ == "__main__":
    main()

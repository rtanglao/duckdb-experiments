#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Plot the August 2025 Bitdefender spike from output/bitdefender_daily.csv.

    uv run sql/plot_bitdefender_spike.py

Runs sql/bitdefender_spike.sql first, so the CSV is always current.

Two series on one axis, both in threads/day, so no dual axis is involved.
This is the emphasis form rather than categorical: Bitdefender carries the
accent hue, total volume recedes to gray as context.

Requires the database to be free of locks -- close the DuckDB UI first.
"""

import csv
import subprocess
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output"
CSV_IN = OUT_DIR / "bitdefender_daily.csv"
PNG_OUT = OUT_DIR / "bitdefender_spike.png"

# Reference palette, light mode. Emphasis: one accent hue + de-emphasis gray.
SURFACE = "#fcfcfb"
ACCENT = "#2a78d6"
CONTEXT = "#898781"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

SPIKE_START, SPIKE_END = date(2025, 8, 11), date(2025, 8, 14)


def load():
    OUT_DIR.mkdir(exist_ok=True)
    subprocess.run(
        ["duckdb", "-readonly", str(ROOT / "thunderbird.duckdb"),
         "-f", str(ROOT / "sql" / "bitdefender_spike.sql")],
        check=True, cwd=ROOT, stdout=subprocess.DEVNULL,
    )
    return list(csv.DictReader(CSV_IN.open()))


def style(ax, days):
    ax.set_facecolor(SURFACE)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=9.5, length=0)
    ax.set_xlim(days[0], days[-1])


def main():
    rows = load()
    days = [date.fromisoformat(r["day"]) for r in rows]
    allq = [int(r["all_questions"]) for r in rows]
    bd = [int(r["bitdefender_questions"]) for r in rows]
    pct = [float(r["pct_bitdefender"]) for r in rows]
    spike = [i for i, d in enumerate(days) if SPIKE_START <= d <= SPIKE_END]

    plt.rcParams["font.family"] = [
        "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans",
    ]
    fig, (ax_n, ax_p) = plt.subplots(
        2, 1, figsize=(11, 7.6), dpi=100, sharex=True,
        gridspec_kw={"hspace": 0.3, "height_ratios": [1.35, 1]},
    )
    fig.patch.set_facecolor(SURFACE)

    fig.text(0.06, 0.968,
             "A Bitdefender update broke Thunderbird for four days",
             color=INK_PRIMARY, fontsize=18, fontweight="bold", va="top")
    fig.text(0.06, 0.920,
             "11–14 August 2025: mail began arriving as raw HTML source with no "
             "subject or sender. 71 threads named Bitdefender — nearly a year's\n"
             "worth in four days — and the forum went from 45 to 81 questions a "
             "day. Daily, Jul–Sep 2025.",
             color=INK_SECONDARY, fontsize=10.5, va="top", linespacing=1.35)

    for ax in (ax_n, ax_p):
        ax.axvspan(SPIKE_START, SPIKE_END, color=ACCENT, alpha=0.07, linewidth=0)

    # --- Counts: emphasis on Bitdefender, total volume as gray context ----
    style(ax_n, days)
    ax_n.plot(days, allq, color=CONTEXT, linewidth=1.4, solid_capstyle="round")
    ax_n.plot(days, bd, color=ACCENT, linewidth=2, solid_capstyle="round")
    ax_n.set_ylim(0, max(allq) * 1.2)
    ax_n.yaxis.set_major_locator(MultipleLocator(25))
    ax_n.set_title("Questions per day", color=INK_SECONDARY, fontsize=11.5,
                   fontweight="bold", loc="left", pad=10)

    # Direct labels stand in for a legend box -- two series, both named here.
    # Anchored in the empty upper-left and along the flat blue baseline, where
    # neither line runs, rather than at the series' right-hand endpoints.
    ax_n.text(days[2], max(allq) * 0.94, "All desktop questions",
              color=CONTEXT, fontsize=10, fontweight="bold", va="center")
    ax_n.text(days[2], max(allq) * 0.09, "Mentioning Bitdefender",
              color=ACCENT, fontsize=10, fontweight="bold", va="center")

    peak = max(spike, key=lambda i: bd[i])
    ax_n.annotate(f"{bd[peak]} on {days[peak]:%-d %b}", (days[peak], bd[peak]),
                  textcoords="offset points", xytext=(0, 11), ha="center",
                  color=INK_PRIMARY, fontsize=10, fontweight="bold")
    ax_n.plot([days[peak]], [bd[peak]], "o", color=ACCENT, markersize=6,
              markeredgecolor=SURFACE, markeredgewidth=2)

    # --- Share ------------------------------------------------------------
    style(ax_p, days)
    ax_p.plot(days, pct, color=ACCENT, linewidth=2, solid_capstyle="round")
    ax_p.set_ylim(0, max(pct) * 1.25)
    ax_p.set_yticks([0, 10, 20, 30], ["0%", "10%", "20%", "30%"])
    ax_p.set_title("Share of that day's questions mentioning Bitdefender",
                   color=INK_SECONDARY, fontsize=11.5, fontweight="bold",
                   loc="left", pad=10)
    top = max(spike, key=lambda i: pct[i])
    ax_p.annotate(f"{pct[top]:.0f}%", (days[top], pct[top]),
                  textcoords="offset points", xytext=(0, 10), ha="center",
                  color=INK_PRIMARY, fontsize=10, fontweight="bold")
    ax_p.plot([days[top]], [pct[top]], "o", color=ACCENT, markersize=6,
              markeredgecolor=SURFACE, markeredgewidth=2)

    fig.text(0.06, 0.03,
             "Source: support.mozilla.org daily scrapes, product=thunderbird. "
             "A thread counts if the question or any answer matches \\bbit ?defender\\b.\n"
             "SUMO moderators appended “(bitdefender)” to many of these titles "
             "during triage, so some threads match the moderator's diagnosis "
             "rather than the reporter's own words.",
             color=INK_MUTED, fontsize=8.5, va="bottom", linespacing=1.6)

    fig.subplots_adjust(left=0.065, right=0.975, top=0.815, bottom=0.135)
    fig.savefig(PNG_OUT, dpi=200, facecolor=SURFACE)
    print(f"wrote {PNG_OUT}")


if __name__ == "__main__":
    main()

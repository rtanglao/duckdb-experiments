#!/usr/bin/env python3
"""Plot Gmail mentions in Thunderbird desktop support questions, by month.

Reads thunderbird.duckdb directly and writes a PNG plus the companion CSV
(the table-view twin of the chart).

    python3 sql/plot_gmail_monthly.py           # loose substring match
    python3 sql/plot_gmail_monthly.py --strict  # Gmail-the-topic only

The loose match is a plain ILIKE '%gmail%' on raw HTML, so it also counts
pasted @gmail.com addresses and gmail strings inside link hrefs. --strict
first deletes @gmail.com addresses from the text, then requires a word
boundary around "gmail", which drops the address-only mentions.

Requires the database to be free of locks -- close the DuckDB UI first.
"""

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
DB = ROOT / "thunderbird.duckdb"
OUT_DIR = ROOT / "output"

STRICT = "--strict" in sys.argv
SUFFIX = "_strict" if STRICT else ""
CSV_OUT = OUT_DIR / f"gmail_monthly{SUFFIX}.csv"
PNG_OUT = OUT_DIR / f"gmail_monthly{SUFFIX}.png"

# Reference palette, light mode. Validated with scripts/validate_palette.js:
# single categorical slot 1 on surface #fcfcfb -- all checks pass.
SURFACE = "#fcfcfb"
SERIES = "#2a78d6"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# Delete @gmail.com addresses, then require a word boundary around "gmail".
# RE2 (DuckDB's regex engine) supports \b.
STRICT_MATCH = (
    r"regexp_matches("
    r"regexp_replace({col}, '[A-Za-z0-9._%+-]+@gmail\.com', '', 'g'),"
    r" '(?i)\bgmail\b')"
)
LOOSE_MATCH = "{col} ILIKE '%gmail%'"

MATCH = STRICT_MATCH if STRICT else LOOSE_MATCH

QUERY = """
SET TimeZone='UTC';
COPY (
    WITH gmail AS (
        SELECT q.id
        FROM questions q
        WHERE """ + MATCH.format(col="q.title") + """
           OR """ + MATCH.format(col="q.content") + """
           OR EXISTS (SELECT 1 FROM answers a
                      WHERE a.question_id = q.id
                        AND """ + MATCH.format(col="a.content") + """)
    )
    SELECT
        date_trunc('month', q.created)::DATE AS month,
        count(*)                             AS all_questions,
        count(g.id)                          AS gmail_questions,
        round(100.0 * count(g.id) / count(*), 2) AS pct_gmail
    FROM questions q
    LEFT JOIN gmail g ON g.id = q.id
    GROUP BY 1
    ORDER BY 1
) TO '{out}' (HEADER);
"""


TEXT_LOOSE = (
    "Gmail keeps ~1 in 7 Thunderbird desktop questions",
    "Questions whose title, body, or any answer mentions “gmail”. "
    "Monthly, Jan 2023 – Jul 2026.",
    "Source: support.mozilla.org daily scrapes, product=thunderbird. "
    "Substring match on raw HTML, so pasted @gmail.com addresses count too.",
)

TEXT_STRICT = (
    "Gmail-the-topic, with pasted addresses stripped out",
    "Same window, stricter match: @gmail.com addresses deleted first, then "
    "“gmail” required as a whole word.",
    "Source: support.mozilla.org daily scrapes, product=thunderbird. "
    "Compare output/gmail_monthly.png, which counts any “gmail” substring.",
)


def load():
    OUT_DIR.mkdir(exist_ok=True)
    subprocess.run(
        ["duckdb", "-readonly", str(DB), "-c", QUERY.format(out=CSV_OUT)],
        check=True,
        cwd=ROOT,
    )
    rows = list(csv.DictReader(CSV_OUT.open()))
    # Drop the trailing partial month -- it is a few days of data and would
    # read as a cliff.
    today = date.today()
    current = f"{today.year:04d}-{today.month:02d}-01"
    return [r for r in rows if r["month"] < current]


def main():
    rows = load()
    months = [date.fromisoformat(r["month"]) for r in rows]
    counts = [int(r["gmail_questions"]) for r in rows]
    pcts = [float(r["pct_gmail"]) for r in rows]

    plt.rcParams["font.family"] = [
        "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans",
    ]

    fig, (ax_n, ax_p) = plt.subplots(
        2, 1, figsize=(10, 7.2), dpi=100, sharex=True,
        gridspec_kw={"hspace": 0.28, "height_ratios": [1, 1]},
    )
    fig.patch.set_facecolor(SURFACE)

    headline, subtitle, source = TEXT_STRICT if STRICT else TEXT_LOOSE
    fig.text(0.055, 0.968, headline,
             color=INK_PRIMARY, fontsize=17, fontweight="600", va="top")
    fig.text(0.055, 0.922, subtitle,
             color=INK_SECONDARY, fontsize=10.5, va="top")

    for ax, values, label in (
        (ax_n, counts, "Questions mentioning Gmail"),
        (ax_p, pcts, "Share of all questions that month"),
    ):
        ax.set_facecolor(SURFACE)
        ax.plot(months, values, color=SERIES, linewidth=1.8,
                solid_capstyle="round")
        ax.set_title(label, color=INK_SECONDARY, fontsize=11,
                     fontweight="600", loc="left", pad=10)
        ax.set_ylim(0, max(values) * 1.16)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8, linestyle="-")
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.spines["bottom"].set_linewidth(0.8)
        ax.tick_params(colors=INK_MUTED, labelsize=9.5, length=0)

        # Direct-label the endpoint and the peak only -- never every point.
        peak = max(range(len(values)), key=lambda i: values[i])
        fmt = (lambda v: f"{v:.0f}") if ax is ax_n else (lambda v: f"{v:.0f}%")
        for i, ha, dx in ((peak, "center", 0), (len(values) - 1, "right", 0)):
            ax.annotate(
                fmt(values[i]), (months[i], values[i]),
                textcoords="offset points", xytext=(dx, 9),
                ha=ha, color=INK_PRIMARY, fontsize=10, fontweight="600",
            )
            ax.plot([months[i]], [values[i]], "o", color=SERIES,
                    markersize=5, markeredgecolor=SURFACE, markeredgewidth=2)

    ax_n.yaxis.set_major_locator(MultipleLocator(50))
    ax_p.set_yticks([0, 5, 10, 15, 20], [f"{t}%" for t in (0, 5, 10, 15, 20)])

    fig.text(0.055, 0.035, source, color=INK_MUTED, fontsize=9, va="bottom")

    fig.subplots_adjust(left=0.075, right=0.965, top=0.845, bottom=0.115)
    fig.savefig(PNG_OUT, dpi=200, facecolor=SURFACE)
    print(f"wrote {PNG_OUT} and {CSV_OUT} ({len(rows)} months)")


if __name__ == "__main__":
    main()

# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this repo is

A **data repository**, not an application. It holds daily scrapes of Mozilla SUMO
(support.mozilla.org) forum data for Thunderbird, used for ad-hoc analysis with
DuckDB. There is no build, no test suite, no package manifest — just CSVs, a few
JSON files, and SQL you write against them.

## Data layout

```
2023/  2024/  2025/  2026/      # one directory per year, ~4000 CSVs total (~120 MB)
  questions-thunderbird-desktop-YYYY-MM-DD.csv
  answers-thunderbird-desktop-YYYY-MM-DD.csv
  questions-thunderbird-android-YYYY-MM-DD.csv
  answers-thunderbird-android-YYYY-MM-DD.csv
```

- One file per **product × record type × day**. `product` is `thunderbird`
  (desktop) or `thunderbird-android`.
- **The CSVs are gitignored here** — they are committed in the
  [`aaq-scraper`](https://github.com/thunderbird/aaq-scraper) repo, which
  produces them on an hourly cron. Don't add them to this repo. A clone without
  them can still build the database from `output/parquet/`.

  Refresh them from a sibling `aaq-scraper` checkout:

  ```bash
  uv run scripts/refresh_csvs.py            # git pull, then mirror
  uv run scripts/refresh_csvs.py --dry-run  # report changes, write nothing
  uv run scripts/refresh_csvs.py --rebuild  # also rebuild the db and Parquet
  ```

  It discovers year directories rather than hardcoding them, so 2027 needs no
  edit, and it mirrors both ways — files the scraper no longer has get deleted
  locally.
- Coverage: desktop is complete for every day 2023-01-01 → present. Android
  starts partial (31 days in 2023, 92 in 2024) and is complete from 2025 on.
- Many daily files are header-only or hold a single row (~424 files are <200
  bytes). This matters for type inference — see gotchas below.
- `2026/*.json` are one-off files from 2026-06-10 only: a JSON mirror of that
  day's questions/answers plus `website-verification-*.json`, which reconciles
  the API/CSV scrape against a browser crawl of the public SUMO question lists.
  The JSON answer schema differs from the CSV one (`question` not `question_id`,
  `num_helpful_votes` not `num_helpful`). Do not mix JSON into CSV loads.

### Columns

`questions-*.csv` (29 columns): `id, created, updated, locale, product, title,
is_solved, solution, solved_by, is_spam, last_answer, answers, topic, tags,
creator, content, involved, is_archived, is_locked, is_taken, metadata,
num_answers, num_votes_past_week, num_votes, taken_until, taken_by, updated_by,
operating_system, thunderbird_version`. A few scrapes also carry
`firefox_version` — hence `union_by_name=true` on every multi-file read.

`answers-*.csv` (9 columns): `id, question_id, created, updated, content,
creator, is_spam, num_helpful, num_unhelpful`.

`content` is raw HTML. `answers`, `tags`, and `involved` are semicolon-delimited
strings, not arrays — split with `string_split(col, ';')`.

## Building the database

```bash
duckdb thunderbird.duckdb -f sql/build_desktop_db.sql   # ~5s, ~155 MB
```

Loads **desktop CSVs only**, 2023–2026: 48,615 questions and 113,103 answers,
each with a `filename` and a derived `file_date` column. Also creates indexes and
a `question_threads` view. `*.duckdb` is gitignored — rebuild rather than commit.

Faster path, and the only one that works without the year directories:

```bash
duckdb thunderbird.duckdb -f sql/build_from_parquet.sql   # ~0.5s
```

`output/parquet/` holds a committed zstd Parquet snapshot of both tables (29 MB
vs 155 MB for the `.duckdb` file). The round-trip is exact — column types
identical, zero rows in either direction of `EXCEPT` — but Parquet carries no
schema objects, so the script recreates the indexes and the view. Regenerate the
snapshot whenever you rebuild from CSVs; the `COPY` statements are in the
script's header comment.

Ad-hoc reads without materializing anything work fine too:

```sql
SELECT count(*) FROM read_csv('2025/questions-thunderbird-*.csv',
                              union_by_name=true, filename=true);
```

## Trusted contributors

Both build scripts `.read sql/trusted_contributors.sql`, which loads
`data/trusted-contributors/*.csv` into a `trusted_contributors` table and defines
three views. An answer **counts** if its author is on the trusted list for the
product **or** is the person who asked the question.

- `answers_scored` — every answer plus `asker`, `by_asker`, `by_trusted`,
  `counts`. Use when you want to slice by author type or compare filtered
  against unfiltered.
- `answers_trusted` — `answers_scored` where `counts`. A drop-in replacement for
  `answers` in any query. Trusted twins exist for all three analyses:
  `sql/gmail_mentions_trusted.sql`, `sql/antivirus_mentions_trusted.sql`, and
  `sql/bitdefender_spike_trusted.sql`; the diff from each unfiltered original is
  one identifier plus `_trusted` output paths. The two plot scripts take
  `--trusted` and write `_trusted` twins of their PNG and CSV.
  **The filter is nearly a no-op for the antivirus work** — it costs
  `_all_antivirus` 81 threads of 3,751 (2.2%) and the Bitdefender spike 1 thread
  of 71, because vendor names appear in the question text far more than in
  answers. Worth knowing before reaching for the filtered variant.
- `question_threads_trusted` — per-question counts, so "unanswered" means
  "nobody who counts answered".

Desktop split of 113,188 answers: 64,760 trusted-only, 38,480 asker-only, 362
both — **9,586 dropped (8.5%)**, being 7,077 untrusted non-askers plus 2,509 with
no verifiable author. The three kept buckets sum exactly to `answers_trusted`;
if they ever don't, suspect a NULL leaking through a comparison.

- **NULL creators need `coalesce`, not a bare `=`.** 2,258 answers have a NULL
  creator and 4,096 hang off a question with a NULL creator (deleted or
  anonymized SUMO accounts). `a.creator = q.creator` is NULL for those, so
  `counts` goes NULL and `WHERE counts` silently discards rows the rule never
  rejected. `answers_scored` coalesces to false and flags them `unattributable`,
  so they are excluded on purpose and stay countable.

- **The name join must be normalized.** Six SUMO usernames start with `@` or `-`
  and the scrape stores them with a leading apostrophe (`'@next`, `'-db-`,
  `'@SteveS`); the trusted list has them bare. A plain `=` join misses `'@next`
  alone — 4,968 answers, the largest apparently-untrusted author in the corpus.
  The `norm_creator()` macro (`lower(ltrim(x, ''''))`) handles it.
- The lists are the metrics repo's, not this one's. Refresh with
  `uv run scripts/refresh_trusted_contributors.py` (`--dry-run` to preview the
  membership diff), then rerun `sql/trusted_contributors.sql`.
- The `count` column is that contributor's answer count *when the list was last
  generated*, and **it is months stale** — `davidsk` is 4,669 there against
  17,801 answers here. Only the `creator` column is used. The last two desktop
  rows (`shopov.bogomil`, `rtanglao`) were hand-appended and will be dropped by
  a regeneration; tracked in
  [metrics#75](https://github.com/thunderbird/thunderbird-metrics-and-reports/issues/75).
- The android list has 3 names and the database is desktop-only, so the android
  half of the table is loaded but unused.

## DuckDB gotchas in this repo

- **Brace globs don't work.** `'{2023,2024}/questions-*.csv'` raises
  "No files found". Pass a list of globs instead:
  `read_csv(['2023/q-*.csv', '2024/q-*.csv'], ...)`.
- **Always `sample_size=-1`** on multi-file reads. The default sample hits the
  many empty/one-row daily files and mis-types columns, which then errors on
  files that actually have data.
- **Always `union_by_name=true`** — column sets vary slightly across scrapes.
- **`SET TimeZone='UTC';` before any date grouping.** `created`/`updated` load as
  `TIMESTAMPTZ`; with a local session timezone, `year(created)` puts 2023-01-01
  UTC rows into 2022. `sql/build_desktop_db.sql` sets it, but an interactive
  session does not inherit that.
- Group by `file_date` (from the filename) when you want "the day it was
  scraped"; group by `created` when you want "the day it was asked". They differ
  at day boundaries.
- **Never `ATTACH ... (READ_ONLY)` in the DuckDB UI** (`duckdb -ui`). The UI
  caches result sets in an in-memory catalog called `localMemDb`; a read-only
  attach blocks that, and the failure surfaces as the misleading
  `Binder Error: Catalog "localmemdb" does not exist!` on a perfectly valid
  query. Use a plain `ATTACH`, or just launch with
  `duckdb -ui thunderbird.duckdb` and let the UI attach it.
- Only one process at a time. A read-write attach takes an exclusive file lock,
  so while the UI holds the database open, a terminal `duckdb thunderbird.duckdb`
  fails to attach — and so does `duckdb -readonly`. Close the UI first.

## Conventions

- Keep reusable SQL in `sql/`. Analyses are exploratory — prefer a readable
  query over a clever one.
- **Python runs through `uv`, never bare `python3` or `pip`.** Scripts carry a
  PEP 723 inline dependency block and the `#!/usr/bin/env -S uv run --script`
  shebang, so `uv run sql/plot_gmail_monthly.py` needs no preinstalled
  environment. Use `fontweight="bold"` in matplotlib rather than numeric
  weights — uv's isolated env has no weight-600 face and falls back with a
  warning.
- Generated artifacts (charts, extracts) go in `output/`, never the repo root.
  Each chart ships with a CSV of the same name as its table-view twin.
- Never edit files under `2023/`–`2026/`; they are scrape output.

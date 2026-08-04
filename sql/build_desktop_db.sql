-- Build thunderbird.duckdb from all thunderbird-desktop CSVs, 2023-2026.
-- Usage (from the repo root):
--   duckdb thunderbird.duckdb -f sql/build_desktop_db.sql
--
-- Notes:
--  * DuckDB's brace glob "{2023,2024}/..." is NOT supported; pass a LIST of globs.
--  * sample_size=-1 scans every row for type inference; many daily files are
--    header-only or a single row, so a small sample mis-types columns.
--  * union_by_name=true tolerates the extra `firefox_version` column that only
--    appears in some scrapes.
--  * `created`/`updated` are TIMESTAMPTZ. Always SET TimeZone='UTC' before
--    grouping by day/year, otherwise local time shifts rows into the wrong
--    date (e.g. 2023-01-01 UTC files land in 2022).

SET TimeZone = 'UTC';

CREATE OR REPLACE TABLE questions AS
SELECT
    *,
    regexp_extract(filename, '(\d{4}-\d{2}-\d{2})\.csv$', 1)::DATE AS file_date
FROM read_csv(
    [
        '2023/questions-thunderbird-desktop-*.csv',
        '2024/questions-thunderbird-desktop-*.csv',
        '2025/questions-thunderbird-desktop-*.csv',
        '2026/questions-thunderbird-desktop-*.csv'
    ],
    union_by_name = true,
    filename = true,
    sample_size = -1
);

CREATE OR REPLACE TABLE answers AS
SELECT
    *,
    regexp_extract(filename, '(\d{4}-\d{2}-\d{2})\.csv$', 1)::DATE AS file_date
FROM read_csv(
    [
        '2023/answers-thunderbird-desktop-*.csv',
        '2024/answers-thunderbird-desktop-*.csv',
        '2025/answers-thunderbird-desktop-*.csv',
        '2026/answers-thunderbird-desktop-*.csv'
    ],
    union_by_name = true,
    filename = true,
    sample_size = -1
);

CREATE INDEX IF NOT EXISTS questions_id_idx ON questions (id);
CREATE INDEX IF NOT EXISTS questions_created_idx ON questions (created);
CREATE INDEX IF NOT EXISTS answers_question_id_idx ON answers (question_id);

-- Convenience view: one row per question with its answer count from `answers`.
CREATE OR REPLACE VIEW question_threads AS
SELECT
    q.*,
    count(a.id) AS answers_present
FROM questions q
LEFT JOIN answers a ON a.question_id = q.id
GROUP BY ALL;

-- trusted_contributors table + answers_trusted / answers_scored /
-- question_threads_trusted views. Reads data/trusted-contributors/*.csv.
.read sql/trusted_contributors.sql

SELECT 'questions' AS tbl, count(*) AS rows, min(created) AS first, max(created) AS last FROM questions
UNION ALL
SELECT 'answers', count(*), min(created), max(created) FROM answers
UNION ALL
SELECT 'answers_trusted', count(*), min(created), max(created) FROM answers_trusted;

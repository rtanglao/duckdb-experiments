-- Zoom in on the Bitdefender spike of August 2025, counting only answers that
-- pass the trusted filter. Derived from sql/bitdefender_spike.sql; the sole
-- difference is `answers` -> `answers_trusted` in the thread temp table.
-- See sql/trusted_contributors.sql.
--
-- Usage (from the repo root):
--   duckdb -readonly thunderbird.duckdb -f sql/bitdefender_spike_trusted.sql
--   uv run sql/plot_bitdefender_spike.py --trusted
--
-- Context: sql/antivirus_mentions.sql shows Bitdefender at 91 threads in
-- 2025 Q3 against a ~10/quarter baseline. Nearly all of it lands in a single
-- week -- 71 threads over four days, 2025-08-11 to 2025-08-14 -- when a
-- Bitdefender update broke Thunderbird's message rendering and mail started
-- arriving as raw HTML source with no subject or sender.
--
-- Writes two files:
--   output/bitdefender_daily_trusted.csv  -- daily counts across a Jul-Sep window
--   output/bitdefender_spike_threads_trusted.csv -- the individual threads
--
-- Caveat worth knowing: SUMO moderators appended "(bitdefender)" to many of
-- these titles during triage, so some threads match on the moderator's
-- diagnosis rather than the reporter's own words. That is real signal about
-- the cause, but it is not the user's language.

SET TimeZone = 'UTC';

CREATE OR REPLACE TEMP TABLE thread AS
SELECT
    q.id, q.created, q.title, q.locale, q.topic, q.is_solved, q.num_answers,
    lower(q.title || ' ' || coalesce(q.content, '') || ' '
          || coalesce(string_agg(a.content, ' '), '')) AS txt
FROM questions q
LEFT JOIN answers_trusted a ON a.question_id = q.id
GROUP BY q.id, q.created, q.title, q.locale, q.topic, q.is_solved,
         q.num_answers, q.content;

COPY (
    SELECT
        created::DATE AS day,
        count(*)      AS all_questions,
        count(*) FILTER (regexp_matches(txt, '\bbit ?defender\b'))
                      AS bitdefender_questions,
        round(100.0 * count(*) FILTER (regexp_matches(txt, '\bbit ?defender\b'))
              / count(*), 2) AS pct_bitdefender
    FROM thread
    WHERE created >= '2025-07-01' AND created < '2025-10-01'
    GROUP BY 1
    ORDER BY 1
) TO 'output/bitdefender_daily_trusted.csv' (HEADER);

COPY (
    SELECT id, created, locale, topic, is_solved, num_answers, title
    FROM thread
    WHERE regexp_matches(txt, '\bbit ?defender\b')
      AND created >= '2025-08-11' AND created < '2025-08-18'
    ORDER BY created
) TO 'output/bitdefender_spike_threads_trusted.csv' (HEADER);

SELECT day, all_questions, bitdefender_questions, pct_bitdefender
FROM read_csv('output/bitdefender_daily_trusted.csv')
WHERE bitdefender_questions > 5
ORDER BY day;

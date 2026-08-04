-- Load the trusted-contributor lists and define the views that analyses use to
-- ignore answers from drive-by accounts.
--
-- Run once against a freshly built database (both build scripts .read this file,
-- so you normally don't invoke it directly):
--   duckdb thunderbird.duckdb -f sql/trusted_contributors.sql
--
-- Source of truth for the lists is the thunderbird-metrics-and-reports repo:
--   CONCATENATED_FILES/DESKTOP/thunderbird-desktop-trusted-contributors.csv
--   CONCATENATED_FILES/ANDROID/thunderbird-android-trusted-contributors.csv
-- Committed copies live in data/trusted-contributors/. Refresh them with
--   uv run scripts/refresh_trusted_contributors.py
--
-- What "counts" as a real answer -- the rule these views encode:
--   the author is on the trusted list for the product, OR
--   the author is the person who asked the question.
-- The second clause matters: 34% of all desktop answers are the asker replying
-- in their own thread ("thanks, that worked", "here is the log you asked for").
-- Dropping those would gut the conversation, so they are kept and flagged
-- separately via by_asker.
--
-- NAME NORMALIZATION -- do not skip this. Six SUMO usernames begin with '@' or
-- '-', and the scrape stores them with a leading apostrophe as a spreadsheet
-- text-guard ('@next, '-db-, '@SteveS, ...). The trusted list has them
-- unguarded (@next). A naive equality join therefore silently misses '@next --
-- 4,968 answers, the single largest supposedly-untrusted author in the corpus.
-- norm_creator() strips the guard and case-folds. No real username starts with
-- an apostrophe, so the ltrim is safe.

CREATE OR REPLACE MACRO norm_creator(x) AS lower(ltrim(x, ''''));

CREATE OR REPLACE TABLE trusted_contributors AS
SELECT DISTINCT 'desktop' AS product, creator, count AS listed_answers
FROM read_csv('data/trusted-contributors/thunderbird-desktop-trusted-contributors.csv')
UNION ALL
SELECT DISTINCT 'thunderbird-android', creator, count
FROM read_csv('data/trusted-contributors/thunderbird-android-trusted-contributors.csv');

-- Every answer, labelled. Use this when you want to slice by author type or
-- compare filtered against unfiltered; use answers_trusted when you just want
-- the filter applied.
CREATE OR REPLACE VIEW answers_scored AS
SELECT
    a.*,
    q.creator                                        AS asker,
    -- coalesce, not a bare `=`. 2,258 answers have a NULL creator and 4,096
    -- hang off a question with a NULL creator (deleted/anonymized SUMO
    -- accounts). Under a bare `=`, by_asker is NULL for those rows, `counts`
    -- becomes NULL, and `WHERE counts` silently discards 2,524 answers that the
    -- rule never actually rejected -- the author buckets then fail to sum to the
    -- row count. Two NULLs are also not evidence of the same person, so NULL
    -- compared to anything is false here, not true.
    coalesce(a.creator = q.creator, false)           AS by_asker,
    t.creator IS NOT NULL                            AS by_trusted,
    -- No verifiable author, so it cannot count -- but it is dropped explicitly
    -- and stays countable, rather than vanishing into a NULL.
    a.creator IS NULL OR q.creator IS NULL           AS unattributable,
    coalesce(a.creator = q.creator, false)
      OR t.creator IS NOT NULL                       AS counts
FROM answers a
JOIN questions q ON q.id = a.question_id
LEFT JOIN trusted_contributors t
       ON t.product = 'desktop'
      AND norm_creator(t.creator) = norm_creator(a.creator);

-- Drop-in replacement for `answers` in any query. Same columns plus the three
-- flags, minus the answers that don't count.
CREATE OR REPLACE VIEW answers_trusted AS
SELECT * FROM answers_scored WHERE counts;

-- One row per question with recomputed answer counts, so "unanswered" means
-- "nobody who counts answered" rather than "no rows in answers".
CREATE OR REPLACE VIEW question_threads_trusted AS
SELECT
    q.*,
    count(a.id)                                AS answers_present,
    count(a.id) FILTER (a.by_trusted)          AS answers_trusted,
    count(a.id) FILTER (a.by_asker)            AS answers_by_asker,
    count(a.id) FILTER (a.by_trusted) > 0      AS has_trusted_answer
FROM questions q
LEFT JOIN answers_trusted a ON a.question_id = q.id
GROUP BY ALL;

SELECT product, count(*) AS names FROM trusted_contributors GROUP BY 1;

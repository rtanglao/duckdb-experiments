-- sql/gmail_mentions.sql, restricted to answers that count: written by a
-- trusted contributor for the product, or by the person who asked. See
-- sql/trusted_contributors.sql for the rule and the name-normalization trap.
--
-- Usage (from the repo root):
--   duckdb -readonly thunderbird.duckdb -f sql/gmail_mentions_trusted.sql
--
-- The only change from the unfiltered version is `answers` -> `answers_trusted`
-- in the two subqueries. The extra in_answer_dropped column is there so a
-- difference is visible rather than silent: it flags threads where Gmail was
-- mentioned ONLY by an answer that got filtered out, i.e. threads this query
-- loses relative to gmail_mentions.sql.
--
-- Filter impact on the 2023-01-01..2026-08-04 desktop corpus: 9,586 of 113,188
-- answers (8.5%) are dropped -- 7,077 untrusted non-askers plus 2,509 with no
-- verifiable author. 6,734 threads match Gmail unfiltered; 6,583 match here, so
-- 151 threads matched only on a dropped answer.
--
-- Same caveat as the unfiltered version: substring match against raw HTML, so
-- it catches @gmail.com addresses and gmail strings inside link hrefs.

SET TimeZone = 'UTC';

SELECT
    q.id,
    q.created::DATE AS asked,
    q.locale,
    q.topic,
    q.is_solved,
    q.num_answers,
    (q.title ILIKE '%gmail%' OR q.content ILIKE '%gmail%') AS in_question,
    EXISTS (SELECT 1 FROM answers_trusted a
            WHERE a.question_id = q.id AND a.content ILIKE '%gmail%') AS in_answer,
    -- Gmail appears only in answers the filter removed.
    NOT (q.title ILIKE '%gmail%' OR q.content ILIKE '%gmail%')
      AND NOT EXISTS (SELECT 1 FROM answers_trusted a
                      WHERE a.question_id = q.id AND a.content ILIKE '%gmail%')
      AND EXISTS (SELECT 1 FROM answers a
                  WHERE a.question_id = q.id AND a.content ILIKE '%gmail%')
      AS in_answer_dropped,
    q.title
FROM questions q
WHERE q.title ILIKE '%gmail%'
   OR q.content ILIKE '%gmail%'
   OR EXISTS (SELECT 1 FROM answers_trusted a
              WHERE a.question_id = q.id AND a.content ILIKE '%gmail%')
ORDER BY q.created DESC;

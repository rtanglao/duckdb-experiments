-- Desktop questions where the question itself, or any of its answers,
-- mentions Gmail. `in_question` / `in_answer` show where the match came from.
--
-- Usage (from the repo root):
--   duckdb -readonly thunderbird.duckdb -f sql/gmail_mentions.sql
--
-- As of the 2023-01-01..2026-08-02 desktop data: 6,724 threads match
-- (4,480 in the question, 3,838 in an answer, 1,594 in both) out of 48,615.
--
-- Caveat: this is a substring match against raw HTML, so it also catches
-- @gmail.com addresses users paste in and gmail strings inside link hrefs.
-- To require a word boundary instead, swap the ILIKEs for
--   regexp_matches(col, '(?i)\bgmail\b')
-- To exclude bare addresses, add   AND q.content NOT ILIKE '%@gmail.com%'

SET TimeZone = 'UTC';

SELECT
    q.id,
    q.created::DATE AS asked,
    q.locale,
    q.topic,
    q.is_solved,
    q.num_answers,
    (q.title ILIKE '%gmail%' OR q.content ILIKE '%gmail%') AS in_question,
    EXISTS (SELECT 1 FROM answers a
            WHERE a.question_id = q.id AND a.content ILIKE '%gmail%') AS in_answer,
    q.title
FROM questions q
WHERE q.title ILIKE '%gmail%'
   OR q.content ILIKE '%gmail%'
   OR EXISTS (SELECT 1 FROM answers a
              WHERE a.question_id = q.id AND a.content ILIKE '%gmail%')
ORDER BY q.created DESC;

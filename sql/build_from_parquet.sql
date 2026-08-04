-- Rebuild thunderbird.duckdb from the committed Parquet snapshot instead of
-- from the 4,000 daily CSVs. Faster (~1s vs ~5s) and needs only output/parquet/,
-- so it works in a clone that doesn't have the year directories.
--
-- Usage (from the repo root):
--   duckdb thunderbird.duckdb -f sql/build_from_parquet.sql
--
-- Fidelity: the Parquet round-trip is exact for both schema and data --
-- verified column-type-identical and zero rows in either direction of
-- (original EXCEPT restored) / (restored EXCEPT original). What Parquet does
-- NOT carry is schema objects: the indexes and the question_threads view are
-- recreated below rather than restored.
--
-- Regenerate the snapshot after rebuilding from CSVs:
--   COPY questions TO 'output/parquet/questions.parquet' (FORMAT parquet, COMPRESSION zstd);
--   COPY answers   TO 'output/parquet/answers.parquet'   (FORMAT parquet, COMPRESSION zstd);

SET TimeZone = 'UTC';

CREATE OR REPLACE TABLE questions AS
FROM read_parquet('output/parquet/questions.parquet');

CREATE OR REPLACE TABLE answers AS
FROM read_parquet('output/parquet/answers.parquet');

CREATE INDEX IF NOT EXISTS questions_id_idx ON questions (id);
CREATE INDEX IF NOT EXISTS questions_created_idx ON questions (created);
CREATE INDEX IF NOT EXISTS answers_question_id_idx ON answers (question_id);

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

SELECT 'questions' AS tbl, count(*) AS rows FROM questions
UNION ALL
SELECT 'answers', count(*) FROM answers
UNION ALL
SELECT 'answers_trusted', count(*) FROM answers_trusted;

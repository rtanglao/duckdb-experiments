-- Antivirus mentions in Thunderbird desktop support threads, by quarter.
--
-- Usage (from the repo root):
--   duckdb -readonly thunderbird.duckdb -f sql/antivirus_mentions.sql
--
-- A "thread" is a question plus all of its answers, lowercased and
-- concatenated once into a temp table so each pattern is one pass over 78 MB
-- of text rather than three correlated subqueries per vendor.
--
-- Matching notes:
--  * Word boundaries throughout (\b), so "reset" does not match ESET and
--    "defenderless" does not match Defender.
--  * \bavg\b was spot-checked against "average" false positives -- the sampled
--    matches were all AVG the vendor.
--  * Norton folds in Symantec; ESET folds in NOD32; Microsoft Defender folds in
--    Windows Defender / Windows Security.
--  * Signature footers ("this email has been checked for viruses by AVG") count
--    as mentions. They are genuine vendor strings but not user complaints.
--  * Bare "AV" (464 threads) is deliberately excluded -- too ambiguous.
--
-- Output is long format: period, series, threads. `series` is either
-- '_all_antivirus' (any of antivirus / anti-virus / anti virus) or a vendor.

SET TimeZone = 'UTC';

CREATE OR REPLACE TEMP TABLE thread AS
SELECT
    q.id,
    q.created,
    lower(q.title || ' ' || coalesce(q.content, '') || ' '
          || coalesce(string_agg(a.content, ' '), '')) AS txt
FROM questions q
LEFT JOIN answers a ON a.question_id = q.id
GROUP BY q.id, q.created, q.title, q.content;

CREATE OR REPLACE TEMP TABLE vendor (name VARCHAR, pat VARCHAR);
INSERT INTO vendor VALUES
    ('Microsoft Defender', '\b(windows|microsoft|ms) defender\b|\bwindows security\b|\bdefender\b'),
    ('Norton',             '\bnorton\b|\bsymantec\b'),
    ('Bitdefender',        '\bbit ?defender\b'),
    ('Avast',              '\bavast\b'),
    ('AVG',                '\bavg\b'),
    ('McAfee',             '\bmc ?afee\b'),
    ('Kaspersky',          '\bkaspersky\b'),
    ('Malwarebytes',       '\bmalwarebytes\b'),
    ('ESET',               '\beset\b|\bnod32\b'),
    ('Avira',              '\bavira\b');

COPY (
    WITH quarters AS (
        SELECT DISTINCT date_trunc('quarter', created)::DATE AS period FROM thread
    ),
    overall AS (
        SELECT date_trunc('quarter', created)::DATE AS period,
               '_all_antivirus' AS series,
               count(*) FILTER (regexp_matches(txt, 'anti[- ]?virus')) AS threads
        FROM thread GROUP BY 1
    ),
    by_vendor AS (
        SELECT date_trunc('quarter', t.created)::DATE AS period,
               v.name AS series,
               count(*) FILTER (regexp_matches(t.txt, v.pat)) AS threads
        FROM thread t CROSS JOIN vendor v
        GROUP BY 1, 2
    ),
    volume AS (
        SELECT date_trunc('quarter', created)::DATE AS period,
               '_all_threads' AS series,
               count(*) AS threads
        FROM thread GROUP BY 1
    )
    SELECT * FROM overall
    UNION ALL SELECT * FROM by_vendor
    UNION ALL SELECT * FROM volume
    ORDER BY series, period
) TO 'output/antivirus_quarterly.csv' (HEADER);

-- Totals, for the record.
SELECT series, sum(threads) AS threads
FROM read_csv('output/antivirus_quarterly.csv')
GROUP BY series
ORDER BY threads DESC;

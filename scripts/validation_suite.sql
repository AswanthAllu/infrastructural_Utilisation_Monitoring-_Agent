-- Validation suite for the db-ops detectors.
-- Run via scripts/run_validation_suite.py, which submits each statement as
-- its own job with use_query_cache=False. Running it as one console script
-- makes the statements sequential, so slot contention can never fire.
--
-- customers_pk is a fixture, created by scripts/fixtures_setup.sql. It is
-- deliberately not recreated here: a CREATE OR REPLACE each run invalidates
-- its cache, and a cached PK join is the only way the tier-0 short-circuit
-- can ever be observed.
--
-- Profile: JOIN_SCALE_PROFILE=sandbox. Nothing here reaches the production
-- floors at this data size.

-- 1. Baseline equi-join, and the only partition-filtered one. Both
--    detectors should stay quiet on the scan.
SELECT
  c.employment_status,
  COUNT(*)                                AS applications,
  ROUND(AVG(l.loan_amount_requested), 2)  AS avg_requested
FROM `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
JOIN `bq-verse-sandbox-052025.banking_data.customers` AS c
  ON c.customer_id = l.customer_id
WHERE l.application_date BETWEEN DATE '2025-01-01' AND DATE '2025-03-31'
GROUP BY 1
ORDER BY applications DESC;

-- 2. Two joins whose keys resolve through CTEs rather than base tables.
--    Covers alias resolution and the only multi-join-stage plan.
WITH tx AS (
  SELECT
    customer_id,
    COUNT(*)                 AS tx_count,
    SUM(transaction_amount)  AS tx_amount
  FROM `bq-verse-sandbox-052025.banking_data.transactions`
  WHERE transaction_date >= DATETIME '2022-01-01'
    AND transaction_date <  DATETIME '2022-02-01'
  GROUP BY customer_id
),
ln AS (
  SELECT
    customer_id,
    COUNT(*)          AS loan_count,
    MAX(cibil_score)  AS best_cibil
  FROM `bq-verse-sandbox-052025.banking_data.loan_applications`
  WHERE application_date BETWEEN DATE '2022-06-05' AND DATE '2025-06-04'
  GROUP BY customer_id
)
SELECT
  c.employment_status,
  COUNT(*)                      AS customers,
  SUM(tx.tx_count)              AS total_transactions,
  SUM(ln.loan_count)            AS total_applications,
  ROUND(AVG(ln.best_cibil), 1)  AS avg_best_cibil
FROM `bq-verse-sandbox-052025.banking_data.customers` AS c
JOIN tx ON tx.customer_id = c.customer_id
JOIN ln ON ln.customer_id = c.customer_id
GROUP BY 1
ORDER BY customers DESC;

-- 3. No aggregation anywhere, so the join stage is not fused. The only
--    statement that ever yields fanout_measurable: true, and the only
--    route to a measured SHUFFLE_VOLUME. Do not add a GROUP BY.
SELECT
  t.customer_id,
  t.transaction_id,
  l.application_id,
  t.transaction_amount,
  l.loan_amount_requested,
  l.loan_status
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
JOIN `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
  ON t.customer_id = l.customer_id;

-- 4. Self-join on a high-NDV key. Ruling-out control: the NDV probe
--    should find it benign rather than firing on every self-join.
SELECT
  a.merchant_category,
  COUNT(*)                         AS paired_rows,
  COUNT(DISTINCT a.customer_id)    AS customers_involved,
  ROUND(AVG(ABS(a.transaction_amount - b.transaction_amount)), 2) AS avg_amount_gap
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS a
JOIN `bq-verse-sandbox-052025.banking_data.transactions` AS b
  ON a.merchant_name = b.merchant_name
 AND a.transaction_id <> b.transaction_id
GROUP BY 1
ORDER BY paired_rows DESC;

-- 5. Computed key that PRESERVES cardinality. Regression guard: this was
--    once misread as a cartesian product. CAST/UPPER/TRIM still hash, so
--    it must classify EQUI_COMPUTED, never UNCONSTRAINED_JOIN.
SELECT
  UPPER(TRIM(t.customer_id))       AS cust_key,
  COUNT(*)                         AS joined_rows,
  SUM(l.loan_amount_requested)     AS total_requested,
  SUM(t.transaction_amount)        AS total_spend
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
JOIN `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
  ON CAST(UPPER(TRIM(t.customer_id)) AS STRING) = CAST(UPPER(TRIM(l.customer_id)) AS STRING)
WHERE CAST(t.transaction_date AS STRING) LIKE '2022-01%'
  AND FORMAT_DATE('%Y', l.application_date) IN ('2022', '2023', '2024', '2025')
GROUP BY 1
ORDER BY joined_rows DESC;

-- 6. Computed key that COLLAPSES cardinality: EXTRACT(DAY) has at most 31
--    values. The only fan-out route readable from the SQL alone, so the
--    only one that survives a cache hit or a low-dominance plan.
--    EXPECT: PROBABLE / FAN_OUT, join_key_expression_collapses_cardinality.
SELECT
  t.merchant_category,
  l.loan_type,
  COUNT(*)                                 AS joined_rows,
  ROUND(AVG(t.transaction_amount), 2)      AS avg_tx_amount,
  ROUND(AVG(l.loan_amount_requested), 2)   AS avg_requested
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
JOIN `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
  ON EXTRACT(DAY FROM t.transaction_date) = EXTRACT(DAY FROM l.application_date)
GROUP BY 1, 2
ORDER BY joined_rows DESC;

-- 7. Self-join on a low-NDV key. The finding counterpart to statement 4.
--    EXPECT: PROBABLE / FAN_OUT at tier 2, from the NDV probe.
SELECT
  a.device_used,
  a.transaction_status,
  COUNT(*)                    AS pair_count,
  SUM(b.transaction_amount)   AS summed_counterparty_amount,
  COUNTIF(a.is_international_transaction AND b.fraud_flag) AS intl_vs_fraud_pairs
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS a
JOIN `bq-verse-sandbox-052025.banking_data.transactions` AS b
  ON a.device_used = b.device_used
GROUP BY 1, 2
ORDER BY pair_count DESC;

-- 8. Join on a boolean: NDV of 2, the extreme of low cardinality. This is
--    the case that showed the plan cannot measure fan-out and motivated
--    tier-2 profiling at all.
SELECT
  l.loan_status,
  t.merchant_category,
  COUNT(*)                                  AS joined_rows,
  ROUND(AVG(l.interest_rate_offered), 3)    AS avg_rate,
  ROUND(AVG(t.transaction_amount), 2)       AS avg_tx_amount
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
JOIN `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
  ON t.fraud_flag = l.fraud_flag
GROUP BY 1, 2
ORDER BY joined_rows DESC;

-- 9. An equality AND a range in the same predicate. Pairs with N6: this
--    one is hash-joinable on the equality, so it must classify EQUI and
--    must NOT be reported as unconstrained.
--    Both sides are partition-filtered so no MISSING_PARTITION_FILTER
--    fires. It was otherwise the only statement referencing two
--    unfiltered partitioned tables, and the incident named whichever one
--    BigQuery listed first — which flipped between runs.
SELECT
  l.loan_type,
  l.loan_status,
  COUNT(DISTINCT l.application_id)     AS applications,
  COUNT(t.transaction_id)              AS tx_in_prior_90d,
  ROUND(SUM(t.transaction_amount), 2)  AS spend_in_prior_90d
FROM `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
JOIN `bq-verse-sandbox-052025.banking_data.transactions` AS t
  ON t.customer_id = l.customer_id
 AND DATE(t.transaction_date)
       BETWEEN DATE_SUB(l.application_date, INTERVAL 90 DAY) AND l.application_date
WHERE l.application_date BETWEEN DATE '2022-06-05' AND DATE '2025-06-04'
  AND t.transaction_date >= DATETIME '2022-01-01'
  AND t.transaction_date <  DATETIME '2022-02-01'
GROUP BY 1, 2
ORDER BY tx_in_prior_90d DESC;

-- 10. Scalar aggregates with no GROUP BY. A different fused-stage shape
--     from the grouped statements above.
SELECT
  APPROX_COUNT_DISTINCT(CONCAT(a.transaction_id, '|', b.transaction_id)) AS distinct_pairs,
  MAX(a.transaction_amount * b.transaction_amount)                       AS max_amount_product,
  MIN(CONCAT(a.merchant_name, '>', b.merchant_name))                     AS min_merchant_pair
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS a
JOIN `bq-verse-sandbox-052025.banking_data.transactions` AS b
  ON a.device_used = b.device_used;

-- D1. Table sizes and join-key NDVs, by hand. Superseded by the tier-2
--     profiler; kept only because it reliably reproduces the SQL text
--     corruption at the diagnosis agent. Drop it once that is fixed.
SELECT
  'transactions'                            AS tbl,
  COUNT(*)                                  AS row_count,
  APPROX_COUNT_DISTINCT(customer_id)        AS ndv_customer_id,
  APPROX_COUNT_DISTINCT(fraud_flag)         AS ndv_fraud_flag,
  APPROX_COUNT_DISTINCT(device_used)        AS ndv_device_used,
  APPROX_COUNT_DISTINCT(merchant_category)  AS ndv_merchant_category,
  APPROX_COUNT_DISTINCT(merchant_name)      AS ndv_merchant_name,
  APPROX_COUNT_DISTINCT(ip_address)         AS ndv_ip_address
FROM `bq-verse-sandbox-052025.banking_data.transactions`
UNION ALL
SELECT
  'loan_applications',
  COUNT(*),
  APPROX_COUNT_DISTINCT(customer_id),
  APPROX_COUNT_DISTINCT(fraud_flag),
  CAST(NULL AS INT64), CAST(NULL AS INT64),
  CAST(NULL AS INT64), CAST(NULL AS INT64)
FROM `bq-verse-sandbox-052025.banking_data.loan_applications`
UNION ALL
SELECT
  'customers',
  COUNT(*),
  APPROX_COUNT_DISTINCT(customer_id),
  CAST(NULL AS INT64), CAST(NULL AS INT64), CAST(NULL AS INT64),
  CAST(NULL AS INT64), CAST(NULL AS INT64)
FROM `bq-verse-sandbox-052025.banking_data.customers`;

-- N1. KEY_SKEW: one hot key, no fan-out. 70% of probe rows carry 'HOT';
--     build holds every key exactly once, so fan-out stays at 1 and skew
--     is the only signal. Build is 2M wide keys to stop BigQuery
--     broadcasting it, which would remove the shuffle and hide the skew.
--     The probe is inflated 200x so the join outweighs generating the
--     build; at 40x the join was only 27% of slot time and the dominance
--     gate rejected it. No DISTINCT anywhere — that was the original
--     version's other defect.
--     EXPECT: CONFIRMED / KEY_SKEW, tier 1, from max_skew_ratio.
WITH probe AS (
  SELECT
    IF(rep <= 140, 'HOT', CONCAT('k_', CAST(rep AS STRING))) AS k,
    t.transaction_amount AS amount
  FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t,
       UNNEST(GENERATE_ARRAY(1, 200)) AS rep
  WHERE t.transaction_date >= DATETIME '2022-01-01'
    AND t.transaction_date <  DATETIME '2022-02-01'
),
build AS (
  SELECT 'HOT' AS k
  UNION ALL
  SELECT CONCAT('k_', CAST(n AS STRING))
  FROM UNNEST(GENERATE_ARRAY(141, 200)) AS n
  UNION ALL
  SELECT LPAD(CONCAT(CAST(a AS STRING), '_', CAST(b AS STRING)), 40, 'p')
  FROM UNNEST(GENERATE_ARRAY(1, 2000)) AS a,
       UNNEST(GENERATE_ARRAY(1, 1000)) AS b
)
SELECT
  COUNT(*)                 AS matched_rows,
  ROUND(SUM(p.amount), 2)  AS amt
FROM probe AS p
JOIN build AS b
  ON p.k = b.k;

-- N2. False-positive control. Same low-NDV key as statement 7, but the
--     other side is two unique rows, so nothing multiplies. A FAN_OUT
--     here would mean the detector reacts to key cardinality rather than
--     to measured behaviour.
SELECT t.merchant_category, COUNT(*) AS n
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
JOIN (SELECT 'Mobile' AS device UNION ALL SELECT 'Desktop') AS d
  ON t.device_used = d.device
GROUP BY 1;

-- N3. Declared PRIMARY KEY on the join key. Values cannot repeat, so the
--     join is ruled out without reading a plan. Reaches the tier-0
--     short-circuit only on a cached run, which is why the fixture is no
--     longer recreated here.
--     EXPECT: NOT_CONFIRMED, declared_primary_key_* .
SELECT c.employment_status, COUNT(*) AS n
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
JOIN `bq-verse-sandbox-052025.banking_data.customers_pk` AS c
  ON c.customer_id = t.customer_id
GROUP BY 1;

-- N4. Outer-join parser coverage. Unit tests cover LEFT; FULL OUTER has
--     only ever been parsed from a real job here.
--     EXPECT: join_type reads "FULL OUTER" in the evidence.
SELECT l.loan_status, COUNT(t.transaction_id) AS tx
FROM `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
FULL OUTER JOIN `bq-verse-sandbox-052025.banking_data.transactions` AS t
  ON t.customer_id = l.customer_id
GROUP BY 1;

-- N5. True cartesian product: no ON, no USING, and the WHERE predicates
--     filter one side each. Both sides are partition-filtered, which
--     isolates the finding from MISSING_PARTITION_FILTER and bounds the
--     cross product.
--     EXPECT: CONFIRMED / UNCONSTRAINED_JOIN, HIGH, tier 0, decided
--     before the size and dominance gates.
SELECT COUNT(*) AS pair_count
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
CROSS JOIN `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
WHERE t.transaction_date BETWEEN '2022-01-01' AND '2022-01-03'
  AND l.application_date BETWEEN '2022-06-05' AND '2022-06-30';

-- N6. The other unconstrained branch: an inequality spanning both tables
--     with no equality anywhere, so there is nothing to hash on. Compare
--     statement 9, which pairs a range WITH an equality and is EQUI.
--     EXPECT: CONFIRMED / UNCONSTRAINED_JOIN, predicate_kind RANGE.
SELECT COUNT(*) AS pair_count
FROM `bq-verse-sandbox-052025.banking_data.transactions` AS t
JOIN `bq-verse-sandbox-052025.banking_data.loan_applications` AS l
  ON t.transaction_amount > l.loan_amount_requested
WHERE t.transaction_date BETWEEN '2022-01-01' AND '2022-01-03'
  AND l.application_date BETWEEN '2022-06-05' AND '2022-06-30';

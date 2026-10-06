-- One-off fixtures for the validation suite. Run once, not per review.
--
-- customers_pk used to live in validation_suite.sql. CREATE OR REPLACE on
-- every run invalidated the table's cache, which meant the PK join was the
-- only statement that always re-executed, and the tier-0 short-circuit
-- (declared_primary_key_on_every_join_key, reached without a plan) could
-- never be observed. It also produced a spurious MISSING_PARTITION_FILTER
-- incident on each review.

CREATE OR REPLACE TABLE `bq-verse-sandbox-052025.banking_data.customers_pk`
(
  customer_id       STRING NOT NULL,
  employment_status STRING,
  PRIMARY KEY (customer_id) NOT ENFORCED
);

INSERT INTO `bq-verse-sandbox-052025.banking_data.customers_pk`
  (customer_id, employment_status)
SELECT customer_id, ANY_VALUE(employment_status)
FROM `bq-verse-sandbox-052025.banking_data.customers`
GROUP BY customer_id;

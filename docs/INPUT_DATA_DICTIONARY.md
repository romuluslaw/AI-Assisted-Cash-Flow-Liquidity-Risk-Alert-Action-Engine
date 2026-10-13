# Input Data Dictionary — Stage 1

All records are synthetic and are intended for demonstration and testing only. Input amounts are non-negative; cash direction is determined by whether the record is a receipt or payment.

## Configuration

### `config/forecast_config.json`

| Field | Meaning | Rule |
|---|---|---|
| `forecast_start_date` | First forecast week start | ISO date (`YYYY-MM-DD`) |
| `opening_cash` | Cash available at forecast start | Finite, non-negative amount |
| `minimum_cash_reserve` | Management-defined minimum reserve | Finite, non-negative amount |
| `currency` | Currency code | Required, non-blank |
| `horizon_weeks` | Forecast length | Exactly 13 |
| `protected_payment_categories` | Categories not eligible for supplier deferral | Explicit list |
| `designated_major_customer_id` | Customer selected for delay scenario | Must match the flagged receipt |
| `designated_major_receipt_id` | Receipt selected for delay scenario | Must match exactly one flagged receipt |
| `ad_hoc_baseline_min_weeks` | Minimum historical coverage | 13 weeks |
| `ad_hoc_baseline_preferred_weeks` | Preferred historical coverage | 26 weeks |

### `config/collection_assumptions.json`

Each timing bucket includes a name, lag-week boundaries and `collection_share`. Shares across all buckets, including `beyond_horizon`, must sum to 100% within the configured tolerance. The profile is illustrative and not an empirical claim about a real company.

## CSV files

### `customer_receipts.csv`

- `transaction_id`: stable unique receipt ID.
- `customer_id`: synthetic customer identifier.
- `expected_date`: expected receipt date; outside-horizon movements remain visible and are flagged.
- `amount`: non-negative receipt amount.
- `is_major_stress_target`: explicit true/false flag; exactly one receipt must match the designated IDs in configuration.

### `known_payments.csv`

- `transaction_id`: stable unique payment ID.
- `category`: payment category.
- `expected_date`: expected payment date.
- `amount`: non-negative payment amount.
- `deferrable`: explicit true/false flag. Protected categories cannot be marked deferrable.

### `historical_claims_payroll.csv`

One aggregated row containing `reference_start_date`, `reference_end_date`, `claims_paid_amount`, and `payroll_amount`. The reference period and payroll basis must be aligned; payroll must be greater than zero to calculate a claims rate.

### `forecast_payroll.csv`

Exactly 13 rows with `week_index` (1–13), `week_start_date`, and `forecast_payroll`.

### `forecast_non_major_sales.csv`

Exactly 13 rows with `week_index` (1–13), `week_start_date`, and `forecast_sales`. This is a supplied sales forecast input, not a separately modelled sales forecast engine.

### `historical_adhoc_payments.csv`

- `transaction_id`: stable unique historical transaction ID.
- `payment_date`: historical payment date.
- `category`: category used for historical baseline grouping.
- `amount`: non-negative historical payment amount.

At least 13 distinct historical weeks are required; 26 weeks are preferred. Shorter or unreliable history must not silently generate a baseline.

# Requirement Traceability — Project 05

| Requirement ID | Approved requirement | Implementation | Test evidence |
|---|---|---|---|
| DATA-01 | Required input files and columns must exist | `src/input_validation.py:REQUIRED_COLUMNS`, `validate_project_inputs` | `test_missing_required_receipt_column_blocks_package` |
| DATA-02 | Amounts are finite and non-negative; payroll denominator must be positive | `_parse_amount` | `test_negative_receipt_amount_blocks_package`, `test_zero_payroll_reference_blocks_claims_rate` |
| DATA-03 | Transaction IDs must be unique and receipt/payment IDs must not collide | `_validate_unique_ids`, cross-stream check | `test_duplicate_transaction_id_blocks_package` |
| DATA-04 | Exactly one designated major receipt must match configured IDs | `validate_project_inputs` major-target check | Valid synthetic fixture; negative cases to be expanded in later test hardening |
| DATA-05 | Forecast payroll and sales must cover weeks 1–13 | Forecast coverage checks in `validate_project_inputs` | `test_forecast_inputs_must_cover_exactly_thirteen_weeks` |
| DATA-06 | Collection shares must reconcile to 100% including beyond-horizon bucket | Collection-assumption check in `validate_project_inputs` | `test_collection_shares_must_reconcile_to_one_hundred_percent` |
| DATA-07 | Historical ad hoc baseline requires 13 weeks minimum; 26 preferred | Historical coverage check in `validate_project_inputs` | `test_thirteen_weeks_of_history_is_minimum_and_twenty_six_is_preferred` |
| DATA-08 | Protected payment categories cannot be deferrable | Protected-category check in `validate_project_inputs` | `test_protected_payment_cannot_be_marked_deferrable` |
| DATA-09 | Beyond-horizon movements are disclosed, not silently discarded | Date-window warning in `validate_project_inputs`; outside-horizon movement records in `src/cash_engine.py` | `test_out_of_horizon_receipt_is_warned_not_silently_discarded`; collection outside-horizon test |
| GOV-01 | Validation status uses Valid / Warning / Blocked | `ValidationReport` | All input-validation tests |
| GOV-02 | Validation findings identify file, rule, component and correction | `ValidationIssue` | Issue-specific validation tests |
| CASH-01 | Weekly closing cash = opening cash + receipts − payments | `_weekly_results` in `src/cash_engine.py` | `test_weekly_roll_forward_matches_independent_hand_calculation` |
| CASH-02 | Opening cash carries forward from prior closing cash | `_weekly_results` | `test_weekly_roll_forward_matches_independent_hand_calculation` |
| CASH-03 | Reserve breach occurs only when closing cash is strictly below reserve | `_weekly_results` | `test_reserve_equality_is_compliant_and_below_reserve_is_breach` |
| CASH-04 | Forecast payroll is included and not double-counted with known scheduled payroll | `_build_payroll_estimates` | `test_forecast_payroll_is_included_as_cash_outflow`; `test_scheduled_payroll_offsets_forecast_payroll_to_prevent_double_counting` |
| CASH-05 | Staff claims estimate = forecast payroll × historical claims/payroll rate | `_build_claims_estimates` | `test_claims_estimate_uses_historical_claims_rate` |
| CASH-06 | Non-major collections follow configured timing buckets and reconcile to sales cohorts | `_build_non_major_collection_estimates` | `test_collection_estimates_reconcile_to_total_sales_cohorts` |
| CASH-07 | Historical ad hoc baseline is category-level; scheduled same-category/week payments reduce estimate, floored at zero | `_build_adhoc_baseline_estimates` | `test_adhoc_estimates_are_weekly_and_explain_baseline_adjustment` |
| CASH-08 | Beyond-horizon cash movements are excluded from forecast totals but retained for disclosure | `_build_known_movements`, `_build_non_major_collection_estimates` | `test_non_major_collection_estimates_are_separate_and_outside_horizon_is_tracked` |
| CASH-09 | Lowest cash, shortfall, first breach, breach weeks and recovery are computed from weekly balances | `calculate_cash_forecast` | Synthetic forecast integration test; edge-case coverage to be expanded |
| CASH-10 | Opening cash below reserve is flagged separately | `calculate_cash_forecast` | `test_opening_cash_below_reserve_is_flagged_separately` |
| CASH-11 | Critical input failure blocks a definitive cash forecast | `calculate_cash_forecast` | `test_critical_invalid_input_blocks_cash_forecast` |
| CASH-12 | Weekly and 13-week roll-forward reconcile | `calculate_cash_forecast` | `test_synthetic_forecast_has_13_reconciled_weeks_and_known_status` |

## Stage boundary

Implemented: input contracts and deterministic base cash engine.

Not yet implemented: adverse scenarios, management actions, AI interpretation, Streamlit dashboard, Windows launcher and full integrated acceptance tests. Their requirements remain in the approved Master Specification and will be added here as their code and tests are built.

## Stage 3 — Scenario transformations

| Requirement | Implementation | Verification |
|---|---|---|
| Base, customer-delay, supplier-deferral, combined and separate acceleration cases | `src/scenario_engine.py::build_scenarios` | `tests/test_scenario_engine.py::test_expected_five_scenarios_are_returned` |
| Recalculate weekly balances and reserve metrics from movement ledger | `src/scenario_engine.py::_recalculate` | `test_every_scenario_reconciles_weekly_and_across_horizon` |
| Delay only designated major customer receipt | `build_scenarios` movement transformation using configured receipt ID | `test_customer_delay_only_changes_designated_major_receipt_date` |
| Defer only explicitly deferrable known payments; protect payroll, taxes, debt and statutory dues | `build_scenarios` eligibility and protected-category checks | `test_supplier_deferral_preserves_payment_amounts_and_total_payments` |
| Deferral is timing-only, not savings | Movement amounts are preserved; action log records `amount_change=0.00` | `test_supplier_deferral_preserves_payment_amounts_and_total_payments` |
| Accelerated receipt remains a separate action | `accelerated_receipt_action` case | `test_accelerated_receipt_is_separate_and_amount_neutral` |
| Compare reserve, shortfall, breach, recovery and outside-horizon obligations | Scenario comparison output | `test_comparison_has_required_metrics` |
| Reject invalid scenario controls | Integer day limits 0–14 | `test_invalid_scenario_controls_are_rejected` |

Scenario output is generated by `python run_scenarios.py` after `python run_cash_forecast.py` and written to `outputs/scenario_results.json`. The engine is deterministic Python; no AI or paid service is called.

## Stage 4 dashboard traceability

| Requirement | Source/output | Presentation or control | Verification status |
|---|---|---|---|
| Block unvalidated assessment | `outputs/validation_report.json` | `load_dashboard_data()` | Source compiled; UI runtime check pending |
| Block unreconciled base case | `outputs/base_forecast.json` | `load_dashboard_data()` | Source compiled; UI runtime check pending |
| Block missing/unreconciled scenarios | `outputs/scenario_results.json` | `load_dashboard_data()` | Source compiled; UI runtime check pending |
| Executive base-case KPIs | Base forecast JSON metrics | `app.py` KPI row, compact SGD-thousands formatting | Python compile passed; browser rendering pending |
| Scenario comparison | Scenario engine `comparison` list | `scenario_table()` compact CFO metrics; detailed outside-horizon totals in audit panel | Python compile passed; browser rendering pending |
| Weekly cash trajectory and reserve | Scenario `weeks` data and base reserve | `cash_trajectory_chart()` chronological x-axis, SGD-thousands y-axis, formatted full-value tooltips | Python compile passed; browser rendering pending |
| Interactive timing stress controls | Validated base movement ledger plus scenario parameters | Customer-delay and supplier-deferral sliders (0–14 days) call `build_scenarios()` in memory | Scenario engine regression suite passed; browser interaction pending |
| Data-quality and audit trail | Validation issues, warnings, movement/action logs | Expanders in `app.py` | Presentation only; no calculation |
| Controlled recalculation | Existing validation/base/scenario scripts | `refresh_outputs()` and sidebar button | Error handling compiled; interactive run pending |

| Requirement | Data field / rule | Implementation | Regression evidence | Dashboard presentation |
|---|---|---|---|---|
| List all known invoice-backed receipts | `customer_receipts.csv`; known receipt movement IDs | `src/scenario_engine.py` builds `invoice_register` | `test_invoice_register_includes_all_known_receipts_and_marks_candidates` | Accelerated receipt action — invoice register |
| Highlight rule-based acceleration candidates | Positive amount; original and seven-day-earlier dates within forecast horizon | `build_scenarios` candidate rule | `test_invoice_register_includes_all_known_receipts_and_marks_candidates` | Eligible candidate / Included in action case / rationale columns |
| Keep acceleration hypothetical and unconfirmed | No source field proves customer agreement | `confirmation_status` | Candidate status assertion in invoice register test | Confirmation status and caution caption |
| Preserve receipt totals | Timing shift only, no amount change | `transform` and `_recalculate` | `test_accelerated_receipt_is_separate_and_amount_neutral`; `test_acceleration_shifts_only_eligible_invoices_and_preserves_amounts` | Gross invoice value moved earlier and timing-only disclosure |

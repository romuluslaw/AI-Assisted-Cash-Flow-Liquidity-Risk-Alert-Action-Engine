# Stage 4 build log — Executive dashboard

## Scope delivered
- Added `app.py`, a Streamlit executive dashboard for base cash KPIs, scenario comparison, selected scenario weekly cash chart, data quality and auditability, and movement/action trail.
- Added `run_dashboard.bat` for Windows virtual-environment setup and dashboard launch.
- Added pinned runtime dependencies for Streamlit and pandas.
- Dashboard calls the deterministic engine scripts only when the user explicitly selects Refresh calculations. It does not call AI or independently calculate financial values.
- Dashboard blocks the assessment if validation or reconciliation gates fail, rather than displaying an unqualified financial assessment.

## Verification
- Stage 3 automated tests are retained as regression coverage.
- `python -m pytest -q`: expected baseline is 35 passing tests; verify exact result in this build environment below.
- `python -m compileall` checks project Python source syntax.
- ZIP integrity checked after packaging.
- Streamlit/pandas could not be installed in this build environment because outbound package index access was unavailable. Consequently, interactive rendering and Windows browser behavior have not been verified here and must be checked on the target Windows machine after dependencies install.

## Known limitation
- Stage 4 is a presentation layer over saved engine outputs. The dashboard does not include AI narrative generation, which remains a later separately gated stage.

## Stage 4.1 — CFO usability corrections (2026-10-12)

### Changes made after reviewer feedback
- KPI amounts are abbreviated in SGD thousands (one decimal place), and the base-case reserve KPI includes the reserve amount.
- Scenario comparison is narrowed to status, lowest cash, first breach, maximum shortfall, breach duration, and recovery; outside-horizon totals remain available in audit details.
- Added customer receipt-delay and eligible supplier-payment-deferral sliders (0–14 days, default 7 days). Scenario calculations are regenerated deterministically in memory from the validated base movement ledger; slider changes do not overwrite persisted outputs.
- Kept accelerated receipt as a separate fixed 7-day action scenario, not combined with stress cases and not a third slider.
- Replaced the inferred chart with an explicit chart specification, chronological week ordering, SGD-thousands axis, and full-value tooltips with thousand separators.
- Executive finding states the first breach week, shortfall, and number of breach weeks.

### Verification
- `python -m pytest -q`: 35 passed.
- `python run_validation.py`: Valid; all 8 required input/config files checked.
- `python run_cash_forecast.py`: completed; Reconciled.
- `python run_scenarios.py`: all five cases generated with expected summary values.
- `python -m py_compile app.py`: passed.
- Full interactive Streamlit/Altair browser rendering was not run in this build environment because Streamlit/Altair are not installed here. Windows browser acceptance remains required.

## Stage 4.2 review refinements (2026-10-12)
- Shortened base-case reserve KPI to `Within reserve` / `Below reserve` while retaining the reserve amount.
- Replaced customer-only executive commentary with four concise scenario-specific findings: customer delay, supplier deferral, combined stress, and the separate accelerated-receipt action.
- Executive findings now state breach week, lowest cash/week, maximum shortfall, breach duration and recovery week where applicable; compliant cases state that no reserve breach is projected.
- Cash trajectory tooltips now display whole SGD amounts with thousand separators, without decimal places. Internal calculations retain cents; chart axis remains SGD thousands with whole-thousand tick labels.
- Receipt acceleration remains a separate predefined 7-day action scenario and is included in the same comparison and findings section. It is intentionally not combined with stress controls.
- Verification in this build environment must be recorded separately from browser/Windows interaction testing; no claim is made that interactive browser rendering has been independently verified here.

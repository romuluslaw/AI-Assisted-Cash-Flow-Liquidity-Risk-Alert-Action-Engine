# Build Log — Stage 2 Deterministic Cash Engine

## Delivered

- `src/cash_engine.py` with Decimal-based weekly cash calculations and traceable movement records.
- `run_cash_forecast.py` to write `outputs/base_forecast.json` and print key metrics.
- Weekly cash roll-forward with known/estimated receipt and payment separation.
- Non-major collection timing-bucket allocations, including tracked outside-horizon amounts.
- Forecast payroll estimates, net of same-week known payroll to avoid double counting.
- Staff claims estimates based on historical claims paid divided by historical payroll.
- Category-level ad hoc payment baseline, with known same-category/week payments deducted and the remainder floored at zero.
- Lowest cash, reserve shortfall, first closing-balance breach, breach-week count, recovery week, opening-cash reserve flag and reconciliation check.
- Automated tests for hand-calculated weekly cash, reserve equality, payroll, claims, collection reconciliation, ad hoc estimates, opening-cash status and blocked input behaviour.
- Updated README and requirement traceability.

## Verification performed in the current build environment

- Python runtime: 3.13.5 (Linux build environment); pytest: 9.0.2.
- `python run_validation.py` → **Valid**; 8 input/config files checked; no warnings or blocked issues in the supplied synthetic fixture (the report contains one informational `Valid` issue record).
- `python -m pytest -q` → **24 passed**.
- `python -m compileall -q src tests data run_validation.py run_cash_forecast.py` → passed.
- `python run_cash_forecast.py` → completed; forecast reconciliation **Reconciled**.
- Production function docstrings were reviewed; every production function has a docstring.
- AI calls and paid services: none used.

## Synthetic base-case result from the current fixture

- Opening cash: SGD 420,000.00.
- Minimum cash reserve: SGD 150,000.00.
- Lowest projected closing cash: SGD 341,057.71 in Week 2.
- Maximum reserve shortfall: SGD 0.00.
- Opening cash below reserve: false.
- First closing-balance breach: none.
- Weeks below reserve: 0.
- Recovery week: not applicable because no closing-balance breach occurs.
- Reconciliation: Reconciled.
- Outside-horizon movements retained for disclosure: 58.

These are outputs from synthetic data and do not establish the adverse-case result.

## Review finding and correction

During review of the first weekly output, forecast payroll was found not to have been included as a separate cash outflow. This would have overstated projected cash. The omission was corrected before the Stage 2 handoff, and regression tests now verify that forecast payroll is included and that a known same-week payroll payment offsets the forecast estimate rather than being double-counted.

## Not yet verified

- Adverse customer delay, supplier deferral, combined scenario and accelerated receipt action.
- AI interpretation and AI-output validation.
- Streamlit dashboard, Windows launcher and full integrated acceptance tests.
- Execution on Windows or specifically under Python 3.11.
- Static lint via Ruff was not run because Ruff is not installed in the current environment.

## Quality boundary

The tests establish the current input-validation and deterministic base-engine behaviour for the supplied fixtures and tested edge cases. They do not prove scenario logic, AI behaviour, dashboard correctness or the full application, which are not implemented yet.

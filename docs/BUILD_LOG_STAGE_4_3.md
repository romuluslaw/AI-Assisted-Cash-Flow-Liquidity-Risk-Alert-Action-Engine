# Stage 4.3 Build Log — Invoice-Level Accelerated Receipt Action

## Approved scope
- Add a visible register of all invoice-backed known receipts.
- Apply a transparent, rule-based candidate rule for the separate accelerated-receipt action.
- Clearly label all candidates as hypothetical and unconfirmed.
- Preserve deterministic Python cash calculations and timing-only movement rules.
- Add regression tests for candidate selection, amount neutrality and movement traceability.

## Candidate rule
A known invoice-backed receipt is a candidate when its amount is positive and both its original expected receipt date and its hypothetical date (seven days earlier by default) fall within the 13-week forecast horizon. All invoice-backed known receipts appear in the register; eligible candidates are highlighted and shifted in the separate action scenario. Candidates are not customer commitments.

The synthetic input does not establish actual customer agreement or commercial feasibility. The register therefore uses `Hypothetical — not confirmed` for candidates. The rule is intended for reproducible demonstration, not as a recommendation that all listed invoices can in reality be accelerated.

## Financial integrity
- Receipt amounts are unchanged; only eligible dates move earlier.
- The accelerated action remains separate from customer-delay and supplier-deferral stress cases.
- The action does not increase total receipts or count any invoice twice.
- The first invoice is excluded from acceleration because moving its date seven days earlier would put it before the forecast start.

## Verification performed
- `python -m pytest -q`: 37 passed.
- `python run_validation.py`: Valid; eight input/config files checked; one informational valid-status issue record.
- `python run_cash_forecast.py`: completed; base case reconciled; lowest cash SGD 341,057.71 in Week 2.
- `python run_scenarios.py`: completed; all five scenarios generated.
- `python -m compileall -q src tests data app.py run_validation.py run_cash_forecast.py run_scenarios.py`: passed.
- Production function docstring audit: no missing docstrings.
- Accelerated receipt register: 9 known invoice-backed receipts listed, 8 eligible candidates; 8 action movements logged.
- Base and accelerated-action total receipts both SGD 1,270,812.49; timing changes only.

## Verification boundary
Automated and deterministic checks passed in the build environment. Interactive Streamlit rendering and user interaction still require launch and visual review on the target Windows environment. No AI calls or paid services were used.

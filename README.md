# Project 05 — AI-Assisted Liquidity Risk Alert & Action Engine

**Build status:** Stages 1–6.3 complete. Input validation, the deterministic 13-week cash engine, five reconciled scenarios, the Streamlit executive dashboard and the local-Ollama CFO narrative (with output guardrails) are implemented, tested and running on the target Windows laptop. See *Deployment issues found and resolved* below.

This is a synthetic mid-market liquidity-risk showcase. The intended end state is a weekly 13-week cash forecast that tests a major-customer receipt delay, eligible supplier deferral and a modelled accelerated-receipt action. Python remains the source of truth for all calculations. AI is used only to interpret validated results into an evidence-backed management narrative; it never calculates or changes a financial figure.

> All included amounts, counterparties and records are fictional. They are not evidence of any real company's liquidity position.

## Delivered so far

### Stage 1 — Foundation and input contracts
- Deterministic synthetic input generator and eight input/configuration files.
- Standard-library input validation with `Valid`, `Warning` and `Blocked` statuses.
- Checks for required fields, amounts, dates, IDs, major receipt designation, protected payment flags, collection shares, forecast coverage, historical coverage and beyond-horizon movements.
- Automated input-validation tests and requirement traceability matrix.

### Stage 2 — Deterministic cash engine
- 13-week opening-to-closing cash roll-forward using `Decimal` currency arithmetic.
- Known invoice-backed receipts and scheduled payments.
- Non-major future-sales collection estimates based on the documented timing buckets; all buckets reconcile to sales, and outside-horizon allocations are retained separately.
- Weekly forecast payroll estimates, net of any same-week known payroll payment to avoid double counting.
- Staff claims estimates based on historical claims paid divided by historical payroll.
- Historical category-level ad hoc payment baselines, less same-category scheduled payments in the same week, floored at zero.
- Lowest cash, reserve shortfall, first closing-balance breach, number of weeks below reserve, recovery week, opening-cash reserve flag and reconciliation status.
- Machine-readable result contract at `outputs/base_forecast.json`.
- Automated unit and integration tests with independent expected values.

## Project structure

```text
Project_05_Liquidity_Risk_Engine/
├── config/
│   ├── forecast_config.json
│   └── collection_assumptions.json
├── data/
│   ├── generate_synthetic_data.py
│   └── input/
├── docs/
│   ├── BUILD_LOG_STAGE_1.md
│   ├── BUILD_LOG_STAGE_2.md
│   ├── INPUT_DATA_DICTIONARY.md
│   └── TRACEABILITY.md
├── outputs/
│   ├── validation_report.json
│   └── base_forecast.json
├── src/
│   ├── input_validation.py
│   └── cash_engine.py
├── tests/
│   ├── test_input_validation.py
│   └── test_cash_engine.py
├── run_validation.py
├── run_cash_forecast.py
├── requirements.txt
└── requirements-dev.txt
└── LICENSE
```

## Requirements

- Python 3.11 or newer is the intended Windows target.
- Runtime calculation and validation modules use the Python standard library.
- Development tests use pinned `pytest==9.0.2`.
- Streamlit and AI-client dependencies will be added only when those components are implemented.

## Run on Windows

Open Command Prompt or PowerShell in the project folder.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python data\generate_synthetic_data.py
python run_validation.py
python -m pytest -q
python run_cash_forecast.py
```

If PowerShell blocks activation, use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

`python run_validation.py` writes `outputs/validation_report.json`. `python run_cash_forecast.py` validates the input package, calculates the deterministic forecast and writes `outputs/base_forecast.json`. A critical validation or calculation failure exits non-zero and does not produce a definitive forecast result.

## Current synthetic base-case result

This is a result from the supplied synthetic fixture only, not a real company's liquidity assessment:

- Overall status: Reserve maintained.
- Lowest projected cash: SGD 341,057.71 in Week 2.
- Configured minimum cash reserve: SGD 150,000.00.
- Maximum reserve shortfall: SGD 0.00.
- Closing-balance reserve breach: none in the base case.
- Reconciliation: Reconciled.
- Outside-horizon movements: 58 tracked records (including estimated collection allocations and other movements assigned outside the 13-week window).

This section describes the Stage 2 base case only. Stress behaviour is covered by the scenario engine (Stage 3); for example, a 7-day delay of the major customer receipt breaches the reserve in Week 4 (see *Headline results* below).

## Auditability standard

Every production function has a docstring explaining its purpose, inputs/outputs or control behaviour. Complex rules are commented where the rationale matters. `docs/TRACEABILITY.md` maps approved requirements to implementation and tests. Future modules must update the matrix and tests as they are added.

## Known limitations (current)

- All data is synthetic; results are decision-support estimates, not predictions or confirmed customer/supplier commitments.
- Unit tests mock the Ollama HTTP response. Live model quality and latency depend on the user's hardware and the installed `gemma4:latest` build and have been verified only on the target Windows laptop (about 36 s per briefing in the final run).
- The accelerated-receipt action shifts dates only and is never combined with the stress scenarios.
- Ruff/static linting has not been run in the build environment.

## Stage 3 — Scenario engine

Run the deterministic scenario cases after refreshing the base forecast:

```bash
python run_cash_forecast.py
python run_scenarios.py
python -m pytest -q
```

The scenario output is `outputs/scenario_results.json`. It contains the base case, a configurable major-customer receipt delay, eligible supplier-payment deferral, the combined stress case, and a separate accelerated-receipt action case. Default timing changes are 7 days; supported scenario controls are integer values from 0 to 14 days. Supplier deferral is a timing shift, not a reduction in payment obligations. Payroll, taxes, debt repayment and statutory dues are protected. Amounts shifted beyond the forecast horizon remain listed and are summarized separately; they are not silently treated as savings. All scenario arithmetic and reconciliation are performed in Python without AI calls.

## Stage 4 — Executive dashboard

The Streamlit dashboard presents the validated base forecast, all five scenario comparisons, the selected weekly cash trajectory, input-validation status, reconciliation status, outside-horizon disclosures, and scenario action logs. It does not calculate financial results and does not call an AI service.

### Launch on Windows

1. Extract the complete project folder.
2. Ensure Python 3.11 or newer is installed and available via the `py` launcher.
3. Double-click `run_dashboard.bat`, or run it from Command Prompt. On first launch it creates `.venv`, installs the pinned runtime and test dependencies, then starts Streamlit.
4. If dependency installation is blocked by a network or corporate proxy, install packages from an approved package source before launching.

To run calculations and tests separately:

```bat
python run_validation.py
python run_cash_forecast.py
python run_scenarios.py
python -m pytest -q
```

The dashboard refuses to display the financial assessment if input validation is not `Valid`, the base forecast is not reconciled, scenario outputs are absent, or any scenario is unreconciled. Use **Refresh calculations** after editing input files; a failed refresh shows an explicit error and stops the refreshed assessment.

### Stage 4 verification boundary

The deterministic engine regression suite from Stage 3 remains the test baseline. Dashboard source compilation and static checks are run during packaging. The Streamlit UI itself must still be launched and visually reviewed in the user's Windows environment because the build environment used for this package had no network access to install Streamlit and pandas. This limitation is disclosed rather than presenting the UI as runtime-tested.

### Stage 4.3 — Invoice-level accelerated receipt action

The dashboard includes an **Accelerated receipt action — invoice register**. It lists every known invoice-backed receipt and highlights candidates for the separate seven-day illustrative action. Candidate eligibility requires a positive amount and both the original and accelerated dates to remain within the 13-week horizon. The register shows invoice reference, customer, amount, original date, hypothetical earlier date, days moved, rationale, and confirmation status. Candidates are labelled **Hypothetical — not confirmed** because the synthetic data does not evidence customer agreement.

The action shifts eligible receipt dates only; it does not change amounts or total receipts and is not combined with stress cases. Review `docs/BUILD_LOG_STAGE_4_3.md` for rules and verification evidence. Current automated suite: 37 tests passed in the build environment; browser rendering still requires Windows verification.

## Stage 5 — AI-ready CFO evidence package (historical stage; Ollama integration was added in Stage 6)

Stage 5 prepares the controlled hand-off for a future, separately approved local Ollama integration. Python remains the financial source of truth. The current version makes **no Ollama, cloud, external AI, or paid service calls**.

### On-demand workflow

1. Use the simulation controls and select the scenario to inspect.
2. Expand **Prepare CFO analysis (AI-ready; no model call)**.
3. Select the intended model tag and planning settings. These are metadata only and do not establish that the model is installed or compatible.
4. Click **Generate CFO Analysis**. The app writes `outputs/cfo_evidence_package.json`, displays a deterministic briefing clearly labelled `PYTHON_RULE_BASED_FALLBACK`, and offers both JSON outputs for download.
5. Review the token budget warning. The estimate uses `ceil(character_count / 3)` as a rough planning heuristic, not the selected model's tokenizer. The exact token count, latency and output quality have not been benchmarked in this environment.

### Proposed local inference settings (not benchmarked)

`config/ai_settings.json` defaults to `gemma4:latest`, 300 seconds, `num_ctx=8192`, and `num_predict=1000`. These are starting configuration values only, not a claim that this model is installed, suitable, or fast on the reviewer's 16 GB laptop. The UI allows the model tag, timeout, context window and output reservation to be changed. The context budget includes the estimated prompt plus reserved output tokens.

These choices reflect `README(4).md`: use an exact model tag from `ollama list`; local model responses can be invalid or stochastic; prompt and output share the context budget; timeout and context must be configurable; and failures must be visible rather than disguised as successful AI output. The previous project's 55-minute run used three sequential calls with `gemma4:26b`; it is not a benchmark for this compact, single-call workload.

### Current controls and limitations

- Evidence package is blocked if input validation is not `Valid`, the base forecast is not reconciled, scenarios are missing/unreconciled, or the selected scenario is invalid.
- The package includes Python-calculated scenario metrics, action assumptions, the invoice register, explicit constraints, model settings and human-review requirement.
- The fallback does not call AI and labels itself as rule-based.
- No Ollama connection check, live token count, inference call, timeout test against a model, or model benchmark is claimed in Stage 5. Those belong to a separately approved integration stage and must be tested on the user's Windows machine.
- No AI narrative is generated automatically on slider movement. The evidence package is created only when the user clicks **Generate CFO Analysis**.

## Stage 6 — local Ollama CFO analysis

- Preferred local model tag: `gemma4:latest`. Confirm the exact installed tag using `ollama list`; the project cannot confirm model availability until run on the target laptop.
- Start Ollama locally, then use **Check local Ollama** in the dashboard. The check targets `127.0.0.1:11434` only.
- Choose one scenario and click **Generate CFO Analysis** to measure that situation. Repeat for Base, Customer Delay, Supplier Deferral, Combined Stress, and Accelerated Receipt Action. Model inference is on-demand; moving sliders alone does not call the model.
- The app reports end-to-end elapsed time, Ollama-reported total duration, model-load duration and token counts when the local service provides them. These are measurements from the user's machine; no benchmark has been performed in the build environment.
- The response must be JSON with required narrative fields, no more than two actions, limitations and `human_review_required=true`. Invalid or timed-out output is rejected and shown as an error; the deterministic Python fallback remains available and is not labelled AI output.
- The financial engine remains authoritative. Ollama is asked to interpret the evidence package and must not calculate or change financial values. Human review is mandatory.
- No cloud provider or paid API is called. `external_or_paid_calls_permitted` remains false. The integration is enabled for explicit local, on-demand use only.
- The invoice register is presented before Data Quality & Auditability. Evidence package and deterministic briefing JSON remain downloadable audit artifacts rather than the primary executive presentation.

### Stage 6 limitations / verification

- Automated unit tests mock the Ollama HTTP response; they do not prove the model is installed, that Windows can reach the service, or that Gemma produces good analysis.
- Live latency, output quality, exact tokenizer/context fit and timeout behaviour must be measured on the target laptop with the actual `gemma4:latest` tag. The prompt token estimate remains a rough heuristic; runtime prompt token counts are captured from Ollama where available.


### Stage 6.1 — fix for non-JSON Gemma responses

If a local generation is rejected as non-JSON, this build sends an explicit JSON Schema to Ollama instead of relying on generic JSON mode. The schema defines all required fields and types, caps management actions at two, and requires human review. Temperature is set to zero for more repeatable structured output. A narrow parser accepts a single valid JSON object wrapped in Markdown fences or a short preamble, but strict schema checks still apply; arbitrary prose remains rejected. If parsing fails, the dashboard error includes a short response preview for diagnosis.

This fix passed the mocked unit tests, but must still be confirmed with a live `gemma4:latest` call on the target laptop. See `docs/BUILD_LOG_STAGE_6_1.md`.


## Stage 6.2 — thinking-model fix and layout
- `gemma4:latest` is a thinking-capable model. Requests now send `think: false` so the output budget is spent on the JSON answer rather than reasoning; this also shortens generation time.
- Schema uses `enum: [true]` rather than `const`. One automatic retry in generic JSON mode occurs if no JSON is returned, within the same overall timeout (default 300 s). Errors report `done_reason` and thinking length.
- Dashboard order: Executive findings, Scenario comparison, CFO analysis, weekly cash chart, **Accelerated receipt invoice register**, Data quality and auditability, Movement audit trail.
- See `docs/BUILD_LOG_STAGE_6_2.md`. Live latency must be measured on the target laptop.


## Stage 6.3 — CFO-ready AI wording
- The model receives Python-prepared plain-English facts (SGD thousands, weeks, headroom/shortfall, base-case comparison, modelled levers) rather than raw JSON. The raw evidence package remains available as an audit download.
- Output is checked: `$` is rewritten to `SGD`; machine-style text or amounts not supplied by Python cause one corrective retry, then a visible rejection.
- The rule-based briefing is displayed only when the AI narrative is unavailable. Timing, token counts and downloads sit under "Technical details and audit files".
- See `docs/BUILD_LOG_STAGE_6_3.md`.


## Headline results (synthetic data, customer delay 7 days, supplier deferral 2 days)

| Scenario | Lowest cash | Reserve | First breach | Shortfall |
|---|---|---|---|---|
| Base | SGD 341.1k (Week 2) | SGD 150.0k | None | — |
| Customer delay (major receipt +7 days) | SGD 146.4k (Week 4) | SGD 150.0k | Week 4 | SGD 3.6k, recovers Week 5 |
| Supplier deferral (2 days) | SGD 341.1k (Week 2) | SGD 150.0k | None | — |
| Combined stress | SGD 146.4k (Week 4) | SGD 150.0k | Week 4 | SGD 3.6k, recovers Week 5 |
| Accelerated receipts (8 invoices, SGD 466.0k, 7 days earlier — hypothetical) | SGD 371.1k (Week 2) | SGD 150.0k | None | — |

The base forecast never approaches the reserve, yet delaying one SGD 280k receipt by seven days takes Week 4 closing cash from SGD 426.4k to SGD 146.4k. No cash is lost; it arrives a week late, which is enough to breach the reserve.

## Deployment issues found and resolved

| # | Symptom on the Windows laptop | Root cause | Fix | Stage |
|---|---|---|---|---|
| 1 | "Ollama is reachable" but **Generate CFO Analysis** failed with `Response preview: ''` | `gemma4:latest` is a *thinking* model (thinking is on by default). Its reasoning consumed the 700-token output limit, leaving an empty answer. The connection itself was healthy | Send `think: false`; raise default output tokens to 1000; use `enum` instead of `const` in the schema; one automatic retry in JSON mode; errors now report `done_reason`, token counts and thinking length | 6.2 |
| 2 | Invoice register appeared above Scenario comparison | Layout order in `app.py` | Moved to after the cash chart and before Data quality and auditability | 6.2 |
| 3 | Evidence bullets looked machine-like (JSON fragments, raw values such as `341057.71`) | The model received the full raw evidence JSON and echoed it | Model now receives Python-prepared plain-English facts in SGD thousands (headroom or shortfall, base-case comparison, modelled levers). Prompt reduced from ~2,300 to ~1,000 tokens | 6.3 |
| 4 | A paragraph rendered as garbled maths text | The model wrote `$…$`; Streamlit treats text between two dollar signs as a LaTeX formula | `$` rewritten to `SGD` after generation and escaped when displayed | 6.3 |
| 5 | Rule-based fallback shown even when the AI succeeded | Fallback block rendered unconditionally | Fallback now appears only when the AI narrative fails or is rejected; timings, token counts and downloads moved to a collapsed "Technical details and audit files" section | 6.3 |
| 6 | Analysis could remain on screen after changing scenario or sliders | Result kept in session state without a signature | Warning shown when the scenario or settings differ from those used to generate the analysis | 6.3 |

### Output guardrails (why the AI text can be trusted)

1. Python computes every figure; the model only rephrases pre-formatted facts.
2. The response must be schema-valid JSON, with at most two actions and `human_review_required=true`.
3. After generation, text is rejected (one corrective retry, then a visible error) if it contains JSON or field names, raw numbers, or an SGD amount that Python did not supply.
4. Failures are shown as failures. The rule-based briefing is clearly labelled as not AI-generated.
5. Everything runs locally; no cloud or paid API is called. Human review is required before any action.

### Windows troubleshooting checklist

- Confirm Ollama is running: `ollama list` should show `gemma4:latest`.
- Check capabilities: `ollama show gemma4:latest`. If *thinking* is listed, keep `think: false` (already set in `src/ollama_client.py`).
- Empty response or `done_reason='length'` in the error text: raise **Reserved output tokens** in the sidebar.
- Timeouts: increase **Timeout (seconds)**; the first call after a restart includes model-load time.
- The sidebar can keep old values during a session; refresh the browser page after changing `config/ai_settings.json`.
- Run the tests with `python -m pytest -q` (69 passing in the build environment).

# Stage 5 build log — AI-ready evidence interface

## Approved scope

- Hardware target: 16 GB RAM laptop.
- Preference: smaller/faster local model; initial metadata default `llama3.2:3b` is a candidate only, not benchmarked.
- Trigger: on-demand button, not slider movement.
- No external AI calls or paid services without separate approval. This stage makes no model calls.
- Python remains the sole financial source of truth.

## Implemented

- `src/ai_ready.py`: validation-gated evidence package, rough token-budget estimate, and explicitly labelled deterministic CFO fallback.
- `config/ai_settings.json`: model tag, timeout, context, output budget, trigger and disabled integration flags.
- Dashboard controls for model tag and planning settings; **Generate CFO Analysis** prepares a JSON evidence package and deterministic fallback only.
- Downloadable evidence package and fallback briefing.
- New regression tests for blocked invalid evidence, selected scenario, preserved metrics, invoice register, budget reservation, fallback provenance and disabled integration.
- README documents setup assumptions and benchmark limitations.

## Verification actually run in build environment

- `python -m pytest -q`: **45 passed**.
- `python run_validation.py`: Valid; 8 files checked; one informational Valid issue record.
- `python run_cash_forecast.py`: Reconciled; lowest cash SGD 341,057.71 in Week 2; no base-case reserve breach.
- `python run_scenarios.py`: completed; base, customer-delay, supplier-deferral, combined-stress and accelerated-receipt outputs generated.
- `python -m compileall -q src tests app.py run_validation.py run_cash_forecast.py run_scenarios.py`: passed.

## Not verified / not claimed

- No live Ollama model call, connection test, model tokenization, latency benchmark, timeout benchmark or output-quality benchmark was run.
- Dashboard browser interaction and Windows launcher were not exercised in this build environment.
- `llama3.2:3b` is a configurable candidate based on the user's preference, not a confirmed recommendation from a measured benchmark.
- The character-based token estimate is heuristic only.

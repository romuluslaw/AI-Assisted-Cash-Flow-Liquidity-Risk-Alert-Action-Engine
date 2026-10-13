# Stage 6.2 Build Log — Gemma "thinking" empty-response fix and layout change

## Reported issues
1. "Check local Ollama" succeeded, but **Generate CFO Analysis** failed with `Response preview: ''`.
2. The invoice register needed to sit after the CFO analysis and before Data quality and auditability.

## Root cause (issue 1)
Evidence from the user's machine: Ollama 0.40.0; `ollama show gemma4:latest` lists the **thinking** capability with default `true`; `ollama run` prints a "Thinking..." block before answering. Through `/api/generate`, a thinking model puts reasoning in a separate `thinking` field and counts it against `num_predict`. With a 700-token cap the budget could be consumed before any answer was written, leaving `response` empty. Stage 6.1 only improved parsing and never set `think`.

## Changes
- `src/ollama_client.py`
  - Sends `"think": false`. If a model rejects the option (HTTP 400 mentioning think), the request is repeated once without it.
  - Schema uses `enum: [true]` instead of `const` (more reliable grammar conversion); Python still validates the value.
  - If the schema-constrained call yields no parseable JSON, **one retry** uses generic `format: "json"`. Retry happens only inside the overall timeout (skipped if under 20 s remain). Connection errors and timeouts are not retried.
  - The error message now includes `done_reason`, generated token count, response length and thinking length for each attempt.
  - Result metadata adds `thinking_requested` and `retry_used`. Strict validation of fields, types, max two actions and `human_review_required=true` is unchanged.
- `config/ai_settings.json`: timeout 600 -> 300 s (single 5-minute budget); `num_predict` 700 -> 1000 (margin for the six-field JSON; the 8192 context budget still fits with ~2,841 input tokens).
- `app.py`: invoice register moved to after the weekly cash chart/caption and before Data quality; stale "no Ollama calls" banner replaced; UI defaults aligned with config; duplicate divider removed.

## Verification (build environment)
- `python -m pytest -q`: 59 passed (5 new tests: think disabled, no `const`, retry on empty response, diagnostics, think-unsupported fallback, no retry on connection failure).
- Streamlit AppTest: app renders without exceptions; expander order CFO analysis -> Invoice register -> Data quality -> Audit trail; simulated empty-then-valid Ollama replies produce a validated narrative.

## Not verified
No live Gemma inference was possible here. Speed on the user's laptop and narrative quality must be confirmed on the target machine. If generation still fails, the error now states `done_reason` and thinking length, which identifies the cause.

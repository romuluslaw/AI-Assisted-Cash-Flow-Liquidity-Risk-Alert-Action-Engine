# Stage 6.3 Build Log — CFO-ready AI wording

## Feedback addressed (from live runs of gemma4:latest, ~80-118 s per scenario)
1. Base case: figures shown as raw numbers (420000.00), not SGD thousands.
2. Combined stress: inconsistent wording; a paragraph rendered as garbled maths.
3. Accelerated receipt / customer delay / supplier deferral: "Evidence" bullets echoed JSON fragments.
4. Rule-based fallback was shown even when the AI succeeded.

## Root causes
- The model was given the full raw evidence JSON (field names, unformatted values, the whole invoice register) and copied it back.
- The model wrote "$146,388.77 ... $150,000.00"; Streamlit treats text between two `$` signs as a LaTeX formula, producing the garbled paragraph.
- The fallback block was rendered unconditionally after any click.

## Changes
- `src/ai_ready.py`: new `build_prompt_facts()` / `fmt_k()`. The model now sees only plain-English facts prepared by Python (SGD thousands, week numbers, headroom or shortfall vs reserve, comparison with base case, other cases for context, modelled levers). Raw evidence remains in the audit download. Prompt budget is now estimated on these facts (~1,000 tokens vs ~2,300).
- `src/ollama_client.py`: new CFO-style prompt (same structure for every scenario; 3-4 one-sentence evidence bullets; amounts copied exactly; no `$`, field names or raw numbers). Python guard after generation: `$` rewritten to `SGD`; output rejected if it contains JSON/field names/raw numbers or an SGD amount that Python did not supply (tolerance SGD 60). A rejected answer triggers one corrective retry inside the overall timeout; if it fails again the reason is shown. `keep_alive` 30 min keeps the model loaded between scenarios.
- `app.py`: `$` escaped when rendering; AI success shows the AI briefing only; the rule-based briefing (renamed "Rule-based briefing") appears only when the AI fails; token/timing detail and audit downloads moved to a "Technical details and audit files" expander; a warning appears if the scenario or sliders changed since the analysis was generated.

## Verification (build environment)
- `python -m pytest -q`: 69 passed.
- Streamlit AppTest with mocked Ollama: success shows AI text only, `$` rendered as SGD; failure shows error plus rule-based briefing; changing scenario shows the stale-analysis warning.

## Not verified
No live Gemma run here. Actual wording quality, speed improvement and how often the guard triggers a retry must be checked on the user's laptop. A retry can add up to one more generation of runtime within the 300 s limit.

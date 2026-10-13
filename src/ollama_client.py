"""Small, local-only Ollama client for evidence-grounded CFO narratives."""
from __future__ import annotations
import json
import re
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from typing import Any

OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def check_ollama(model_name: str, timeout_seconds: int = 10, base_url: str = OLLAMA_BASE_URL) -> dict[str, Any]:
    """Check local Ollama availability and whether the requested model tag exists."""
    request = Request(f"{base_url}/api/tags", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            tags = json.loads(response.read().decode("utf-8"))
        names = [item.get("name", "") for item in tags.get("models", [])]
        return {"available": True, "model_found": model_name in names, "model_name": model_name, "installed_models": names}
    except (URLError, HTTPError, TimeoutError, ValueError, OSError) as exc:
        return {"available": False, "model_found": False, "model_name": model_name, "error": f"{type(exc).__name__}: {exc}"}



def _extract_json_object(response_text: Any) -> dict[str, Any] | None:
    """Extract a single balanced JSON object from common Markdown-wrapped output."""
    if not isinstance(response_text, str):
        return None
    text = response_text.strip()
    # First remove a single outer Markdown code fence when present.
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None

_REQUIRED_KEYS = ("finding", "evidence", "risk", "recommended_management_action", "limitations", "human_review_required")


def _output_schema() -> dict[str, Any]:
    """JSON Schema passed to Ollama's ``format`` field.

    ``enum: [true]`` is used instead of ``const`` because Ollama's schema-to-grammar
    conversion handles enum more reliably; Python re-checks the value afterwards.
    """
    return {
        "type": "object",
        "properties": {
            "finding": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "risk": {"type": "string"},
            "recommended_management_action": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
            "limitations": {"type": "array", "items": {"type": "string"}},
            "human_review_required": {"type": "boolean", "enum": [True]},
        },
        "required": list(_REQUIRED_KEYS),
        "additionalProperties": False,
    }


def _post_generate(base_url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    """POST to /api/generate. If the model rejects the ``think`` option, retry once without it."""
    def _send(body: dict[str, Any]) -> dict[str, Any]:
        request = Request(f"{base_url}/api/generate", data=json.dumps(body).encode("utf-8"),
                          headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        with urlopen(request, timeout=max(1, int(timeout_seconds))) as response:
            return json.loads(response.read().decode("utf-8"))
    try:
        return _send(payload)
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - diagnostics only
            pass
        if exc.code == 400 and "think" in detail.lower() and "think" in payload:
            reduced = {k: v for k, v in payload.items() if k != "think"}
            try:
                return _send(reduced)
            except (URLError, HTTPError, TimeoutError, ValueError, OSError) as retry_exc:
                raise RuntimeError(f"Local Ollama request failed: {type(retry_exc).__name__}: {retry_exc}") from retry_exc
        raise RuntimeError(f"Local Ollama request failed: {type(exc).__name__}: {exc} {detail[:200]}".strip()) from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise RuntimeError(f"Local Ollama request failed: {type(exc).__name__}: {exc}") from exc


def _parse_model_json(response_text: Any) -> dict[str, Any] | None:
    """Return a JSON object from the model text, or None if none can be found."""
    try:
        value = json.loads(response_text)
        if isinstance(value, dict):
            return value
    except (TypeError, ValueError):
        pass
    return _extract_json_object(response_text)


_CURRENCY_FIX = re.compile(r"\$\s*(?=\d)")
_AMOUNT = re.compile(r"SGD\s*(\d[\d,]*(?:\.\d+)?)\s*([kK])?")
_MACHINE_PATTERNS = (
    (re.compile(r"[{}\[\]]"), "contains JSON brackets"),
    (re.compile(r'"\s*\w+\s*"\s*:'), "contains JSON key/value text"),
    (re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b"), "contains machine field names"),
    (re.compile(r"\b\d{5,}(?:\.\d+)?\b|\b\d+\.\d{2}\b"), "contains unformatted raw numbers"),
)


def _text_fields(result: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten the narrative's text fields as (field, text) pairs, tolerating bad types."""
    pairs: list[tuple[str, str]] = []
    for key in ("finding", "risk"):
        if isinstance(result.get(key), str):
            pairs.append((key, result[key]))
    for key in ("evidence", "recommended_management_action", "limitations"):
        value = result.get(key)
        if isinstance(value, list):
            pairs += [(key, item) for item in value if isinstance(item, str)]
    return pairs


def _normalise_currency(result: dict[str, Any]) -> None:
    """Rewrite '$146,000' as 'SGD 146,000'. A bare dollar sign is wrong for SGD and is also
    interpreted by Streamlit as a maths delimiter, which garbles the rendered paragraph."""
    for key in ("finding", "risk"):
        if isinstance(result.get(key), str):
            result[key] = _CURRENCY_FIX.sub("SGD ", result[key])
    for key in ("evidence", "recommended_management_action", "limitations"):
        if isinstance(result.get(key), list):
            result[key] = [_CURRENCY_FIX.sub("SGD ", x) if isinstance(x, str) else x for x in result[key]]


def _amounts(text: str) -> list[float]:
    values = []
    for match in _AMOUNT.finditer(text):
        value = float(match.group(1).replace(",", ""))
        values.append(value * 1000 if match.group(2) else value)
    return values


def _style_issues(result: dict[str, Any], facts: str | None) -> list[str]:
    """Return reasons the narrative is not CFO-ready: machine-style text or figures not supplied by Python."""
    issues: list[str] = []
    allowed = _amounts(facts) if facts else None
    for field, text in _text_fields(result):
        for pattern, reason in _MACHINE_PATTERNS:
            if pattern.search(text):
                issues.append(f"{field} {reason}")
                break
        if allowed is not None:
            for value in _amounts(text):
                if not any(abs(value - ok) <= 60 for ok in allowed):
                    issues.append(f"{field} uses an SGD amount not supplied by Python (SGD {value:,.0f})")
                    break
    return list(dict.fromkeys(issues))


def _diagnostics(raw: dict[str, Any]) -> str:
    """Compact, non-sensitive description of an Ollama reply for error messages."""
    return (f"done_reason={raw.get('done_reason')!r}; generated_tokens={raw.get('eval_count')}; "
            f"response_chars={len(str(raw.get('response', '') or ''))}; "
            f"thinking_chars={len(str(raw.get('thinking', '') or ''))}")


def generate_cfo_analysis(evidence: dict[str, Any], model_name: str, timeout_seconds: int,
                          num_ctx: int, num_predict: int, base_url: str = OLLAMA_BASE_URL) -> dict[str, Any]:
    """Generate and validate a CFO narrative using only a local Ollama endpoint.

    Financial values are passed as evidence; the model is instructed not to calculate
    or change them. The function measures end-to-end HTTP generation time and rejects
    malformed or incomplete JSON rather than silently presenting it as valid analysis.

    Reasoning ("thinking") is disabled: thinking-capable models such as gemma4 otherwise
    spend the output-token budget on reasoning and can return an empty ``response``.
    If the schema-constrained call returns no parseable JSON, one retry is made with
    generic JSON mode inside the same overall timeout. Python validation is unchanged.
    """
    budget = evidence.get("prompt_budget", {})
    if not budget.get("within_configured_context", False):
        raise ValueError("Estimated prompt plus reserved output exceeds the configured context; reduce the evidence or adjust settings.")
    facts = (evidence.get("model_view") or {}).get("prompt_facts")
    instructions = (
        "You are drafting a short liquidity briefing for a CFO. Python is authoritative: use ONLY the facts supplied below. "
        "Never calculate, round, change or invent figures, dates, probabilities, commitments or approvals. "
        "Write for a CFO in plain, professional business English. "
        "Amounts: copy them exactly as written in the facts (for example 'SGD 341.1k'); never use the $ symbol, never write raw numbers such as 341057.71, "
        "and never mention field names, identifiers with underscores, or JSON. Refer to scenarios by their plain names (for example 'Customer delay'). "
        "Return ONLY valid JSON with exactly these keys: finding (string), evidence (array of strings), risk (string), "
        "recommended_management_action (array of at most 2 strings), limitations (array of strings), human_review_required (boolean, must be true). "
        "finding: one or two sentences that lead with the reserve conclusion for the scenario under review. "
        "evidence: 3 or 4 bullets, each one complete sentence of at most 25 words, rephrasing the supplied facts (reserve position, lowest cash and week, comparison with the base case). "
        "risk: one sentence. If the reserve is maintained, say so and do not manufacture a crisis; if it is breached, state how large and when. "
        "recommended_management_action: at most 2 specific actions drawn from the modelled levers, each stating who must confirm it (for example the collections owner or treasury); "
        "do not recommend anything the facts do not support. limitations: one short sentence. "
        "Use the same structure and tone for every scenario."
    )
    if facts:
        prompt = instructions + "\n\nFACTS PREPARED BY PYTHON:\n" + facts
    else:  # backwards-compatible path for callers that supply only the raw evidence package
        prompt = instructions + "\n\nEVIDENCE JSON:\n" + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    base_payload = {"model": model_name, "stream": False, "think": False, "keep_alive": "30m",
                    "options": {"num_ctx": int(num_ctx), "num_predict": int(num_predict), "temperature": 0.0}}
    started = time.perf_counter()
    deadline = started + int(timeout_seconds)
    raw: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    retry_used = False
    diagnostics: list[str] = []
    style_issues: list[str] = []
    retry_note = ""
    next_format: Any = _output_schema()
    for index in range(2):
        remaining = deadline - time.perf_counter()
        if index > 0 and remaining < 20:
            break  # not enough of the overall time budget left for a meaningful retry
        label = "json_schema" if index == 0 else "retry"
        raw = _post_generate(base_url, {**base_payload, "prompt": prompt + retry_note, "format": next_format}, remaining)
        parsed = _parse_model_json(raw.get("response", ""))
        if parsed is None:
            diagnostics.append(f"{label}: {_diagnostics(raw)}")
            next_format = "json"
            retry_note = "\n\nIMPORTANT: reply with the JSON object only."
            continue
        _normalise_currency(parsed)
        found = _style_issues(parsed, facts)
        if found:
            style_issues = found
            diagnostics.append(f"{label}: not CFO-ready ({'; '.join(found)})")
            next_format = _output_schema()
            retry_note = ("\n\nIMPORTANT: your previous answer was rejected (" + "; ".join(found) +
                          "). Rewrite it as plain CFO-style sentences using only the SGD amounts shown in the facts.")
            continue
        result, style_issues, retry_used = parsed, [], index > 0
        break
    elapsed = time.perf_counter() - started
    if result is None and style_issues:
        raise ValueError("Ollama output rejected because it is not CFO-ready after one retry: "
                         + "; ".join(style_issues) + ". Diagnostics: " + " | ".join(diagnostics))
    if result is None:
        preview = str(raw.get("response", "")).strip().replace("\n", " ")[:180]
        raise ValueError(
            "Ollama did not return a parseable JSON object, even with schema-constrained output. "
            f"Response preview: {preview!r}. Diagnostics: {' | '.join(diagnostics)}. "
            "If done_reason is 'length' or thinking_chars is above 0, increase reserved output tokens "
            "or confirm thinking is disabled."
        )
    required = set(_REQUIRED_KEYS)
    if not isinstance(result, dict) or not required.issubset(result):
        raise ValueError("Ollama output failed schema validation: required fields are missing.")
    if not isinstance(result["finding"], str) or not isinstance(result["risk"], str):
        raise ValueError("Ollama output failed schema validation: finding and risk must be strings.")
    if not isinstance(result["evidence"], list) or not all(isinstance(x, str) for x in result["evidence"]):
        raise ValueError("Ollama output failed schema validation: evidence must be an array of strings.")
    actions = result["recommended_management_action"]
    if not isinstance(actions, list) or len(actions) > 2 or not all(isinstance(x, str) for x in actions):
        raise ValueError("Ollama output failed schema validation: provide at most two string actions.")
    if not isinstance(result["limitations"], list) or not all(isinstance(x, str) for x in result["limitations"]):
        raise ValueError("Ollama output failed schema validation: limitations must be an array of strings.")
    if result["human_review_required"] is not True:
        raise ValueError("Ollama output rejected: human_review_required must be true.")
    result.update({"status": "OLLAMA_LOCAL_VALIDATED", "ai_called": True, "model_name": model_name,
                   "generation_seconds": round(elapsed, 3), "ollama_total_duration_seconds": round(raw.get("total_duration", 0) / 1_000_000_000, 3),
                   "ollama_load_duration_seconds": round(raw.get("load_duration", 0) / 1_000_000_000, 3),
                   "prompt_eval_count": raw.get("prompt_eval_count"), "generation_eval_count": raw.get("eval_count"),
                   "prompt_estimated_tokens": budget.get("estimated_input_tokens"),
                   "context_tokens": int(num_ctx), "reserved_output_tokens": int(num_predict),
                   "thinking_requested": False, "retry_used": retry_used,
                   "human_review_required": True, "external_calls_performed": False})
    return result

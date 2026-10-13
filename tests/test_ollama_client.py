"""Tests for local Ollama response handling without requiring Ollama installed."""
import json
from unittest.mock import patch
import pytest
from src.ollama_client import check_ollama, generate_cfo_analysis

class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.payload).encode()


def valid_evidence():
    return {"prompt_budget": {"within_configured_context": True, "estimated_input_tokens": 200}}


def valid_model_output():
    return {"response": json.dumps({"finding":"Reserve maintained.","evidence":["Reconciled"],"risk":"Assumption risk.","recommended_management_action":["Confirm assumptions."],"limitations":["Synthetic data."],"human_review_required":True})}


def test_check_ollama_reports_model_found():
    with patch("src.ollama_client.urlopen", return_value=FakeResponse({"models":[{"name":"gemma4:latest"}]})):
        assert check_ollama("gemma4:latest")["model_found"] is True


def test_generate_returns_elapsed_and_local_provenance():
    with patch("src.ollama_client.urlopen", return_value=FakeResponse(valid_model_output())):
        result = generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 700)
    assert result["status"] == "OLLAMA_LOCAL_VALIDATED"
    assert result["ai_called"] is True
    assert result["generation_seconds"] >= 0
    assert result["external_calls_performed"] is False


def test_generate_blocks_over_budget_prompt():
    evidence = {"prompt_budget": {"within_configured_context": False}}
    with pytest.raises(ValueError, match="exceeds"):
        generate_cfo_analysis(evidence, "gemma4:latest", 30, 8192, 700)


def test_generate_rejects_missing_fields():
    with patch("src.ollama_client.urlopen", return_value=FakeResponse({"response":"{}"})):
        with pytest.raises(ValueError, match="required fields"):
            generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 700)


def test_generate_rejects_more_than_two_actions():
    output = json.loads(valid_model_output()["response"])
    output["recommended_management_action"] = ["a", "b", "c"]
    with patch("src.ollama_client.urlopen", return_value=FakeResponse({"response":json.dumps(output)})):
        with pytest.raises(ValueError, match="at most two"):
            generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 700)


def test_generate_rejects_missing_human_review():
    output = json.loads(valid_model_output()["response"])
    output["human_review_required"] = False
    with patch("src.ollama_client.urlopen", return_value=FakeResponse({"response":json.dumps(output)})):
        with pytest.raises(ValueError, match="human_review_required"):
            generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 700)


def test_generate_uses_schema_constrained_json_format():
    with patch("src.ollama_client.urlopen", return_value=FakeResponse(valid_model_output())) as mocked:
        generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 700)
    request = mocked.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert isinstance(payload["format"], dict)
    assert payload["format"]["type"] == "object"
    assert payload["format"]["additionalProperties"] is False
    assert payload["options"]["temperature"] == 0.0


def test_generate_accepts_markdown_fenced_json_but_validates_schema():
    output = json.loads(valid_model_output()["response"])
    wrapped = {"response": "```json\\n" + json.dumps(output) + "\\n```"}
    with patch("src.ollama_client.urlopen", return_value=FakeResponse(wrapped)):
        result = generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 700)
    assert result["status"] == "OLLAMA_LOCAL_VALIDATED"


def test_generate_rejects_non_json_with_response_preview():
    with patch("src.ollama_client.urlopen", return_value=FakeResponse({"response": "Here is the analysis, but no JSON."})):
        with pytest.raises(ValueError, match="Response preview"):
            generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 700)


# ---- Stage 6.2: thinking-model empty-response fix ----
import io
from urllib.error import HTTPError


def _sent_payloads(mocked):
    return [json.loads(call.args[0].data.decode("utf-8")) for call in mocked.call_args_list]


def test_generate_disables_thinking_and_avoids_const_in_schema():
    with patch("src.ollama_client.urlopen", return_value=FakeResponse(valid_model_output())) as mocked:
        generate_cfo_analysis(valid_evidence(), "gemma4:latest", 30, 8192, 1000)
    payload = _sent_payloads(mocked)[0]
    assert payload["think"] is False
    assert "const" not in json.dumps(payload["format"])
    assert payload["format"]["properties"]["human_review_required"]["enum"] == [True]


def test_empty_response_triggers_one_json_mode_retry_then_succeeds():
    empty = FakeResponse({"response": "", "thinking": "reasoning...", "done_reason": "length", "eval_count": 700})
    with patch("src.ollama_client.urlopen", side_effect=[empty, FakeResponse(valid_model_output())]) as mocked:
        result = generate_cfo_analysis(valid_evidence(), "gemma4:latest", 60, 8192, 1000)
    payloads = _sent_payloads(mocked)
    assert len(payloads) == 2
    assert isinstance(payloads[0]["format"], dict)
    assert payloads[1]["format"] == "json" and payloads[1]["think"] is False
    assert result["retry_used"] is True and result["status"] == "OLLAMA_LOCAL_VALIDATED"


def test_empty_response_both_attempts_reports_diagnostics():
    empty = {"response": "", "thinking": "x" * 50, "done_reason": "length", "eval_count": 700}
    with patch("src.ollama_client.urlopen", side_effect=[FakeResponse(empty), FakeResponse(empty)]):
        with pytest.raises(ValueError, match="done_reason='length'.*thinking_chars=50"):
            generate_cfo_analysis(valid_evidence(), "gemma4:latest", 60, 8192, 1000)


def test_model_without_think_support_is_retried_without_think_option():
    err = HTTPError("http://x", 400, "Bad Request", {}, io.BytesIO(b'{"error":"model does not support thinking"}'))
    with patch("src.ollama_client.urlopen", side_effect=[err, FakeResponse(valid_model_output())]) as mocked:
        result = generate_cfo_analysis(valid_evidence(), "other:model", 60, 8192, 1000)
    payloads = _sent_payloads(mocked)
    assert "think" in payloads[0] and "think" not in payloads[1]
    assert result["status"] == "OLLAMA_LOCAL_VALIDATED"


def test_connection_failure_is_not_retried():
    from urllib.error import URLError
    with patch("src.ollama_client.urlopen", side_effect=URLError("refused")) as mocked:
        with pytest.raises(RuntimeError, match="Local Ollama request failed"):
            generate_cfo_analysis(valid_evidence(), "gemma4:latest", 60, 8192, 1000)
    assert mocked.call_count == 1


# ---- Stage 6.3: CFO-ready wording guard ----
def evidence_with_facts():
    ev = valid_evidence()
    ev["model_view"] = {"prompt_facts": "Reserve SGD 150.0k. Lowest cash SGD 146.4k in Week 4, SGD 3.6k below reserve."}
    return ev


def model_reply(**overrides):
    body = {"finding": "Customer delay breaches the SGD 150.0k reserve in Week 4.", "evidence": ["Lowest cash reaches SGD 146.4k in Week 4."],
            "risk": "Shortfall of SGD 3.6k for one week.", "recommended_management_action": ["Collections owner to confirm the receipt date."],
            "limitations": ["Synthetic data."], "human_review_required": True}
    body.update(overrides)
    return FakeResponse({"response": json.dumps(body)})


def test_prompt_uses_preformatted_facts_not_raw_json():
    with patch("src.ollama_client.urlopen", return_value=model_reply()) as mocked:
        generate_cfo_analysis(evidence_with_facts(), "gemma4:latest", 60, 8192, 1000)
    prompt = _sent_payloads(mocked)[0]["prompt"]
    assert "FACTS PREPARED BY PYTHON" in prompt and "EVIDENCE JSON" not in prompt
    assert "SGD 146.4k" in prompt and "never use the $ symbol" in prompt


def test_dollar_signs_are_rewritten_to_sgd():
    reply = model_reply(finding="Cash of $146.4k is below the $150.0k reserve.")
    with patch("src.ollama_client.urlopen", return_value=reply):
        result = generate_cfo_analysis(evidence_with_facts(), "gemma4:latest", 60, 8192, 1000)
    assert "$" not in result["finding"] and "SGD 146.4k" in result["finding"]


def test_machine_style_evidence_is_rejected_then_retried():
    bad = model_reply(evidence=['"selected_scenario":{"lowest_cash":"146388.77"}'])
    with patch("src.ollama_client.urlopen", side_effect=[bad, model_reply()]) as mocked:
        result = generate_cfo_analysis(evidence_with_facts(), "gemma4:latest", 120, 8192, 1000)
    payloads = _sent_payloads(mocked)
    assert len(payloads) == 2 and "was rejected" in payloads[1]["prompt"]
    assert result["retry_used"] is True and "{" not in result["evidence"][0]


def test_machine_style_evidence_rejected_after_retry_shows_reason():
    bad = model_reply(evidence=["base_case: opening_cash: 420000.00"])
    with patch("src.ollama_client.urlopen", side_effect=[bad, bad]):
        with pytest.raises(ValueError, match="not CFO-ready"):
            generate_cfo_analysis(evidence_with_facts(), "gemma4:latest", 120, 8192, 1000)


def test_amount_not_supplied_by_python_is_rejected():
    invented = model_reply(risk="Shortfall of SGD 9.9k in Week 4.")
    with patch("src.ollama_client.urlopen", side_effect=[invented, invented]):
        with pytest.raises(ValueError, match="not supplied by Python"):
            generate_cfo_analysis(evidence_with_facts(), "gemma4:latest", 120, 8192, 1000)


def test_full_sgd_amount_matching_rounded_k_figure_is_accepted():
    reply = model_reply(risk="Shortfall of SGD 3,611 in Week 4.")
    with patch("src.ollama_client.urlopen", return_value=reply):
        assert generate_cfo_analysis(evidence_with_facts(), "gemma4:latest", 60, 8192, 1000)["status"] == "OLLAMA_LOCAL_VALIDATED"

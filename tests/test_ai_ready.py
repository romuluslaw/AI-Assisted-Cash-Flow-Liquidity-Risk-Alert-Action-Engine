"""Regression tests for the AI-ready evidence contract and no-AI fallback."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.ai_ready import build_evidence_package, deterministic_cfo_brief, estimate_tokens

ROOT = Path(__file__).resolve().parents[1]


def sample_data():
    """Load the checked-in synthetic outputs as test fixtures."""
    base = json.loads((ROOT / "outputs" / "base_forecast.json").read_text(encoding="utf-8"))
    scenarios = json.loads((ROOT / "outputs" / "scenario_results.json").read_text(encoding="utf-8"))
    validation = json.loads((ROOT / "outputs" / "validation_report.json").read_text(encoding="utf-8"))
    return validation, base, scenarios


def package(selected="customer_delay"):
    """Build the common valid evidence package used by regression tests."""
    validation, base, scenarios = sample_data()
    return build_evidence_package(validation, base, scenarios, selected,
                                  model_name="llama3.2:3b", num_ctx=8192, num_predict=700, timeout_seconds=600)


def test_estimate_tokens_is_positive_and_conservative_heuristic():
    """Token estimate is deterministic and documented as a heuristic."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcdef") == 2


def test_evidence_package_preserves_authoritative_financial_metrics():
    """Package carries engine values unchanged and does not calculate alternatives."""
    evidence = package()
    validation, base, scenarios = sample_data()
    selected = next(item for item in scenarios["scenarios"] if item["scenario_id"] == "customer_delay")
    assert evidence["base_case"]["lowest_cash"] == base["lowest_cash"]
    assert evidence["selected_scenario"]["lowest_cash"] == selected["lowest_cash"]
    assert evidence["external_calls_performed"] is False
    assert evidence["human_review_required"] is True


def test_evidence_package_includes_invoice_register_and_scenario_comparison():
    """CFO narrative input retains traceable invoice and scenario evidence."""
    evidence = package("accelerated_receipt_action")
    assert evidence["accelerated_receipt_register"]
    assert {x["scenario_id"] for x in evidence["scenario_comparison"]} >= {
        "base", "customer_delay", "supplier_deferral", "combined_stress", "accelerated_receipt_action"
    }


def test_blocks_invalid_validation_and_unreconciled_results():
    """Invalid financial evidence must never reach the narrative interface."""
    validation, base, scenarios = sample_data()
    invalid = deepcopy(validation)
    invalid["overall_status"] = "Blocked"
    with pytest.raises(ValueError, match="validation"):
        build_evidence_package(invalid, base, scenarios, "base", model_name="x", num_ctx=8192, num_predict=700)
    unreconciled = deepcopy(base)
    unreconciled["reconciliation_status"] = "Unreconciled"
    with pytest.raises(ValueError, match="base forecast"):
        build_evidence_package(validation, unreconciled, scenarios, "base", model_name="x", num_ctx=8192, num_predict=700)


def test_blocks_missing_selected_scenario():
    """A non-existent scenario ID cannot be narrated."""
    validation, base, scenarios = sample_data()
    with pytest.raises(ValueError, match="selected scenario"):
        build_evidence_package(validation, base, scenarios, "not-a-scenario", model_name="x", num_ctx=8192, num_predict=700)


def test_budget_check_reserves_output_tokens():
    """Budget check includes both estimated prompt tokens and output reservation."""
    evidence = package()
    budget = evidence["prompt_budget"]
    assert budget["estimated_total_budget"] == budget["estimated_input_tokens"] + budget["reserved_output_tokens"]
    assert isinstance(budget["within_configured_context"], bool)


def test_fallback_is_explicitly_not_ai_generated_and_contains_required_sections():
    """Failure-safe CFO briefing has clear provenance and human-review language."""
    brief = deterministic_cfo_brief(package())
    assert brief["status"] == "PYTHON_RULE_BASED_FALLBACK"
    assert brief["ai_called"] is False
    assert brief["human_review_required"] is True
    assert brief["finding"]
    assert brief["evidence"]
    assert brief["risk"]
    assert len(brief["recommended_management_action"]) <= 2


def test_model_settings_enable_local_only_on_demand_integration():
    """Local inference is enabled, but only on explicit user action."""
    settings = json.loads((ROOT / "config" / "ai_settings.json").read_text(encoding="utf-8"))
    assert settings["integration_enabled"] is True
    assert settings["provider"] == "ollama_localhost"
    assert settings["model_name"] == "gemma4:latest"
    assert settings["external_or_paid_calls_permitted"] is False
    assert settings["trigger"] == "on_demand"


# ---- Stage 6.3: CFO-readable model input ----
from src.ai_ready import fmt_k


def test_fmt_k_uses_sgd_thousands():
    assert fmt_k("341057.71") == "SGD 341.1k"
    assert fmt_k(3611.23) == "SGD 3.6k"


def test_model_facts_are_cfo_formatted_with_no_raw_json_or_field_names():
    facts = package("combined_stress")["model_view"]["prompt_facts"]
    assert "SGD 351.4k" in facts and "SGD 150.0k" in facts
    assert "{" not in facts and "_" not in facts          # no JSON, no snake_case identifiers
    assert "341057.71" not in facts and "$" not in facts   # no raw numbers, no dollar signs


def test_facts_cover_base_comparison_and_levers_for_every_scenario():
    for scenario_id in ("base", "customer_delay", "supplier_deferral", "combined_stress", "accelerated_receipt_action"):
        facts = package(scenario_id)["model_view"]["prompt_facts"]
        assert "KEY FIGURES FOR THIS SCENARIO" in facts and "OTHER CASES" in facts
        assert "SGD 466.0k" in facts  # accelerated-receipt lever is always available as context


def test_prompt_budget_is_based_on_compact_facts():
    evidence = package()
    assert evidence["prompt_budget"]["estimated_input_tokens"] < 1500

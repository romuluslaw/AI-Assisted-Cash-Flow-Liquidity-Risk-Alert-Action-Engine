"""AI-ready evidence packaging and deterministic CFO briefing fallback.

No network or Ollama calls are made in this module. Python financial outputs
remain authoritative; this module prepares a compact, auditable hand-off for a
future separately approved local-model integration.
"""
from __future__ import annotations

import json
from typing import Any


SCENARIO_LABELS = {
    "base": "Base case",
    "customer_delay": "Customer delay",
    "supplier_deferral": "Supplier deferral",
    "combined_stress": "Combined stress",
    "accelerated_receipt_action": "Accelerated receipt action",
}


PROMPT_OVERHEAD_TOKENS = 500  # rough allowance for the fixed instructions around the facts


def fmt_k(value: Any) -> str:
    """Format an SGD amount in thousands, e.g. 341057.71 -> 'SGD 341.1k'."""
    return f"SGD {float(value) / 1000:,.1f}k"


def _scenario_line(item: dict[str, Any], reserve: float, base_lowest: float | None) -> str:
    """One CFO-readable sentence for a scenario, using only Python-computed values."""
    label = SCENARIO_LABELS.get(item["scenario_id"], item["scenario_id"])
    low = float(item["lowest_cash"])
    shortfall = float(item["maximum_reserve_shortfall"])
    if shortfall > 0:
        line = (f"{label}: reserve breached from Week {item['first_breach_week']}; lowest closing cash "
                f"{fmt_k(low)} in Week {item['lowest_cash_week']}, {fmt_k(shortfall)} below the {fmt_k(reserve)} reserve; "
                f"below reserve for {item['breach_week_count']} week(s)")
        line += (f"; back above reserve in Week {item['recovery_week']}." if item.get("recovery_week") else ".")
    else:
        line = (f"{label}: reserve maintained; lowest closing cash {fmt_k(low)} in Week {item['lowest_cash_week']}, "
                f"{fmt_k(low - reserve)} above the {fmt_k(reserve)} reserve.")
    if base_lowest is not None and item["scenario_id"] != "base":
        diff = low - base_lowest
        if abs(diff) >= 50:
            line += f" Lowest cash is {fmt_k(abs(diff))} {'higher' if diff > 0 else 'lower'} than the base case ({fmt_k(base_lowest)})."
    return line


def build_prompt_facts(base: dict[str, Any], scenarios: list[dict[str, Any]], selected_id: str,
                       register: list[dict[str, Any]]) -> str:
    """Pre-format every figure the model may use as plain CFO-readable text.

    The model is shown these sentences instead of raw JSON so that it cannot echo field
    names or unformatted numbers, and so that every amount is already in SGD thousands.
    """
    reserve = float(base["minimum_cash_reserve"])
    by_id = {item["scenario_id"]: item for item in scenarios}
    base_item = by_id.get("base")
    base_lowest = float(base_item["lowest_cash"]) if base_item else None
    selected = by_id[selected_id]
    lines = [
        f"SCENARIO UNDER REVIEW: {SCENARIO_LABELS.get(selected_id, selected_id)}",
        f"What changes in this scenario: {'No stress or action applied; this is the baseline forecast.' if selected_id == 'base' else (selected.get('description') or 'Not stated.')}",
        f"Opening cash: {fmt_k(base['opening_cash'])}. Minimum cash reserve: {fmt_k(reserve)}. Horizon: {base.get('horizon_weeks', 13)} weeks.",
        "", "KEY FIGURES FOR THIS SCENARIO:", f"- {_scenario_line(selected, reserve, base_lowest)}",
        "", "OTHER CASES (context only):",
    ]
    for item in scenarios:
        if item["scenario_id"] != selected_id:
            lines.append(f"- {_scenario_line(item, reserve, base_lowest)}")
    chosen = [r for r in register if r.get("selected_for_action")]
    lever_lines = []
    accel = by_id.get("accelerated_receipt_action")
    if accel and chosen:
        total = sum(float(r["outstanding_amount"]) for r in chosen)
        lever_lines.append(f"- Bringing {len(chosen)} eligible invoices ({fmt_k(total)} in total) forward by 7 days is modelled as a separate hypothetical action; "
                           f"lowest cash would be {fmt_k(accel['lowest_cash'])} in Week {accel['lowest_cash_week']}. It moves timing only and needs customer agreement.")
    supplier = by_id.get("supplier_deferral")
    if supplier:
        lever_lines.append("- Deferring eligible supplier payments is a timing change only and needs supplier agreement; payroll, tax, statutory dues and debt repayment are protected.")
    if lever_lines:
        lines += ["", "MANAGEMENT LEVERS ALREADY MODELLED:"] + lever_lines
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Return a conservative rough token estimate from character count.

    This is a planning heuristic only; the exact tokenizer depends on the
    selected model and is not available without querying that model.
    """
    return (len(text) + 2) // 3


def build_evidence_package(
    validation: dict[str, Any],
    base: dict[str, Any],
    scenario_payload: dict[str, Any],
    selected_scenario_id: str,
    *,
    model_name: str,
    num_ctx: int,
    num_predict: int,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Build a compact, JSON-safe evidence package from validated outputs.

    The function blocks invalid or unreconciled financial results and includes
    only computed metrics, scenario parameters and traceable action evidence.
    """
    if validation.get("overall_status") != "Valid":
        raise ValueError("Evidence package blocked: input validation is not Valid.")
    if base.get("reconciliation_status") != "Reconciled":
        raise ValueError("Evidence package blocked: base forecast is not reconciled.")
    scenarios = scenario_payload.get("scenarios", [])
    if not scenarios or any(s.get("reconciliation_status") != "Reconciled" for s in scenarios):
        raise ValueError("Evidence package blocked: scenario results are missing or unreconciled.")
    by_id = {item.get("scenario_id"): item for item in scenarios}
    if selected_scenario_id not in by_id:
        raise ValueError("Evidence package blocked: selected scenario is not present.")

    def metrics(item: dict[str, Any]) -> dict[str, Any]:
        """Select relevant already-calculated metrics without recalculating them."""
        return {
            "scenario_id": item.get("scenario_id"),
            "description": item.get("description"),
            "lowest_cash": item.get("lowest_cash"),
            "lowest_cash_week": item.get("lowest_cash_week"),
            "first_breach_week": item.get("first_breach_week"),
            "maximum_reserve_shortfall": item.get("maximum_reserve_shortfall"),
            "breach_week_count": item.get("breach_week_count"),
            "recovery_week": item.get("recovery_week"),
            "reconciliation_status": item.get("reconciliation_status"),
        }

    evidence = {
        "schema_version": "1.0",
        "analysis_type": "synthetic_liquidity_risk_cfo_briefing",
        "authority": "Python financial outputs are authoritative; AI must not recalculate figures.",
        "human_review_required": True,
        "external_calls_performed": False,
        "validation": {"overall_status": validation.get("overall_status")},
        "base_case": {
            "opening_cash": base.get("opening_cash"),
            "minimum_cash_reserve": base.get("minimum_cash_reserve"),
            "lowest_cash": base.get("lowest_cash"),
            "lowest_cash_week": base.get("lowest_cash_week"),
            "reconciliation_status": base.get("reconciliation_status"),
        },
        "selected_scenario": metrics(by_id[selected_scenario_id]),
        "scenario_comparison": [metrics(item) for item in scenarios],
        "scenario_parameters": scenario_payload.get("parameters", {}),
        "accelerated_receipt_register": scenario_payload.get("invoice_register", []),
        "constraints": [
            "Do not invent facts, probabilities, customer commitments or supplier approvals.",
            "Use only the supplied evidence; distinguish facts, estimates and assumptions.",
            "Use Finding -> Evidence -> Risk -> Recommended management action.",
            "Recommend no more than two actions and state required human confirmations.",
            "Do not alter or recalculate any financial metric.",
        ],
        "model_settings": {
            "model_name": model_name,
            "num_ctx": int(num_ctx),
            "num_predict": int(num_predict),
            "timeout_seconds": int(timeout_seconds),
            "token_estimate_method": "ceil(characters / 3) of the pre-formatted facts plus a fixed instruction allowance; rough planning estimate only",
        },
    }
    # The model sees only this pre-formatted text; the full evidence stays in the audit download.
    evidence["model_view"] = {"prompt_facts": build_prompt_facts(base, scenarios, selected_scenario_id,
                                                                 scenario_payload.get("invoice_register", []))}
    token_estimate = estimate_tokens(evidence["model_view"]["prompt_facts"]) + PROMPT_OVERHEAD_TOKENS
    evidence["prompt_budget"] = {
        "estimated_input_tokens": token_estimate,
        "context_tokens": int(num_ctx),
        "reserved_output_tokens": int(num_predict),
        "estimated_total_budget": token_estimate + int(num_predict),
        "within_configured_context": token_estimate + int(num_predict) <= int(num_ctx),
        "warning": "Estimate is heuristic; exact tokenization requires the selected model.",
    }
    return evidence


def deterministic_cfo_brief(evidence: dict[str, Any]) -> dict[str, Any]:
    """Create a clearly labelled no-AI fallback from validated Python metrics."""
    selected = evidence["selected_scenario"]
    reserve = float(evidence["base_case"]["minimum_cash_reserve"])
    lowest = float(selected["lowest_cash"])
    shortfall = float(selected["maximum_reserve_shortfall"])
    breach = selected.get("first_breach_week")
    finding = (
        f"{SCENARIO_LABELS.get(selected['scenario_id'], selected['scenario_id'])}: "
        f"lowest projected closing cash is SGD {lowest:,.0f} in Week {selected['lowest_cash_week']}."
    )
    if shortfall > 0:
        finding += (f" Reserve breach begins in Week {breach}; maximum reserve shortfall is "
                    f"SGD {shortfall:,.0f} against the SGD {reserve:,.0f} reserve, across "
                    f"{selected['breach_week_count']} week(s).")
    else:
        finding += f" The SGD {reserve:,.0f} minimum reserve is maintained in this scenario."
    if selected.get("recovery_week"):
        finding += f" Recovery above reserve is projected in Week {selected['recovery_week']}."
    return {
        "status": "PYTHON_RULE_BASED_FALLBACK",
        "ai_called": False,
        "finding": finding,
        "evidence": [
            f"Input validation: {evidence['validation']['overall_status']}.",
            f"Selected scenario reconciliation: {selected['reconciliation_status']}.",
            f"Scenario: {selected.get('description') or selected['scenario_id']}.",
        ],
        "risk": "This is a scenario under stated assumptions, not a prediction or confirmed customer/supplier commitment.",
        "recommended_management_action": [
            "Confirm the key receipt and payment timing assumptions with accountable owners.",
            "Review invoice-level and payment-movement evidence before approving any intervention.",
        ],
        "human_review_required": True,
    }

"""Independent integrity tests for deterministic scenario transformations."""
from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from src.scenario_engine import ScenarioEngineError, build_scenarios

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def results():
    """Calculate the standard scenario set from the generated base forecast."""
    with (ROOT / "outputs/base_forecast.json").open(encoding="utf-8") as handle:
        base = json.load(handle)
    return build_scenarios(base, ROOT)


def test_expected_five_scenarios_are_returned(results):
    """Ensure stress cases and the separately selected action case are present."""
    assert [item["scenario_id"] for item in results["scenarios"]] == [
        "base", "customer_delay", "supplier_deferral", "combined_stress", "accelerated_receipt_action"
    ]


def test_every_scenario_reconciles_weekly_and_across_horizon(results):
    """Verify weekly roll-forwards and final cash against independent arithmetic."""
    for scenario in results["scenarios"]:
        weeks = scenario["weeks"]
        assert scenario["reconciliation_status"] == "Reconciled"
        for index, week in enumerate(weeks):
            expected = (Decimal(week["opening_cash"]) + Decimal(week["total_receipts"])
                        - Decimal(week["total_payments"]))
            assert expected == Decimal(week["closing_cash"])
            if index:
                assert Decimal(weeks[index - 1]["closing_cash"]) == Decimal(week["opening_cash"])
        final_expected = (Decimal(scenario["opening_cash"]) + Decimal(scenario["total_receipts"])
                          - Decimal(scenario["total_payments"]))
        assert final_expected == Decimal(weeks[-1]["closing_cash"])


def test_supplier_deferral_preserves_payment_amounts_and_total_payments(results):
    """Confirm supplier deferral shifts eligible dates but never claims savings."""
    base, deferred = results["scenarios"][0], results["scenarios"][2]
    assert base["total_payments"] == deferred["total_payments"]
    base_amounts = {m["movement_id"]: m["amount"] for m in base["movements"]}
    deferred_amounts = {m["movement_id"]: m["amount"] for m in deferred["movements"]}
    assert base_amounts == deferred_amounts
    moved = [a for a, b in zip(base["movements"], deferred["movements"])
             if a["movement_date"] != b["movement_date"]]
    assert moved
    assert all(m["category"] not in {"Payroll", "Taxes", "Debt Repayment", "Statutory Dues"}
               for m in moved if m["direction"] == "payment")


def test_customer_delay_only_changes_designated_major_receipt_date(results):
    """Ensure the customer stress case shifts only the designated receipt timing."""
    base, delayed = results["scenarios"][0], results["scenarios"][1]
    base_by_id = {m["movement_id"]: m for m in base["movements"]}
    delayed_by_id = {m["movement_id"]: m for m in delayed["movements"]}
    changed = [key for key in base_by_id if base_by_id[key]["movement_date"] != delayed_by_id[key]["movement_date"]]
    assert changed == ["RCPT_MAJOR_001"]
    assert base_by_id[changed[0]]["amount"] == delayed_by_id[changed[0]]["amount"]


def test_accelerated_receipt_is_separate_and_amount_neutral(results):
    """Check the optional acceleration is a separate timing-only action scenario."""
    action = results["scenarios"][4]
    assert action["scenario_id"] == "accelerated_receipt_action"
    assert len(action["action_log"]) == 8
    assert all(item["action"] == "accelerated_receipt_action" for item in action["action_log"])
    assert all(item["amount_change"] == "0.00" for item in action["action_log"])
    assert action["total_receipts"] == results["scenarios"][0]["total_receipts"]


def test_comparison_has_required_metrics(results):
    """Ensure each comparison row exposes the agreed management metrics."""
    required = {"lowest_cash", "first_breach_week", "maximum_reserve_shortfall", "breach_week_count",
                "recovery_week", "reserve_restored_for_horizon", "outside_horizon_movement_count"}
    assert all(required.issubset(row) for row in results["comparison"])


@pytest.mark.parametrize("kwargs", [
    {"customer_delay_days": -1}, {"customer_delay_days": 15},
    {"supplier_deferral_days": 2.5}, {"accelerated_receipt_days": True},
])
def test_invalid_scenario_controls_are_rejected(kwargs):
    """Reject controls outside the explicitly approved integer 0–14 day range."""
    with (ROOT / "outputs/base_forecast.json").open(encoding="utf-8") as handle:
        base = json.load(handle)
    with pytest.raises(ScenarioEngineError):
        build_scenarios(base, ROOT, **kwargs)


def test_input_base_is_not_mutated(results):
    """Protect the original forecast object from scenario side effects."""
    with (ROOT / "outputs/base_forecast.json").open(encoding="utf-8") as handle:
        base = json.load(handle)
    before = deepcopy(base)
    build_scenarios(base, ROOT)
    assert base == before


def test_invoice_register_includes_all_known_receipts_and_marks_candidates(results):
    """Expose every invoice-backed known receipt and distinguish eligible hypothetical candidates."""
    register = results["invoice_register"]
    assert len(register) == 9
    candidates = [row for row in register if row["eligible_candidate"]]
    assert len(candidates) == 8
    assert all(row["confirmation_status"] == "Hypothetical — not confirmed" for row in candidates)
    assert all(row["selected_for_action"] for row in candidates)
    assert all(row["outstanding_amount"] for row in register)
    assert "13-week forecast horizon" in results["acceleration_rule"]


def test_acceleration_shifts_only_eligible_invoices_and_preserves_amounts(results):
    """Ensure invoice candidates are moved earlier once without altering receipt amounts."""
    base, action = results["scenarios"][0], results["scenarios"][4]
    base_by_id = {m["movement_id"]: m for m in base["movements"]}
    action_by_id = {m["movement_id"]: m for m in action["movements"]}
    shifted = {key for key in base_by_id if base_by_id[key]["movement_date"] != action_by_id[key]["movement_date"]}
    expected = {row["invoice_reference"] for row in results["invoice_register"] if row["eligible_candidate"]}
    assert shifted == expected
    assert all(base_by_id[key]["amount"] == action_by_id[key]["amount"] for key in shifted)

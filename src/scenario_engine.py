"""Deterministic scenario transformations for Project 05 liquidity forecasts.

This module performs no AI calls. It transforms traceable movement dates, then
recalculates weekly cash balances and reserve metrics from the movement ledger.
"""
from __future__ import annotations

import csv
import json
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
PROTECTED = {"Payroll", "Taxes", "Debt Repayment", "Statutory Dues"}


class ScenarioEngineError(RuntimeError):
    """Raised when scenario inputs or transformed forecast data are invalid."""


def _money(value: Any) -> Decimal:
    """Parse a finite currency value and normalize it to two decimal places."""
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ScenarioEngineError(f"Invalid currency value: {value!r}.") from exc
    if not amount.is_finite():
        raise ScenarioEngineError(f"Currency value must be finite: {value!r}.")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _index_for(tx_date: date, start: date, horizon: int) -> int | None:
    """Return the one-based forecast week for a date, or None outside horizon."""
    offset = (tx_date - start).days
    if offset < 0:
        return None
    index = offset // 7 + 1
    return index if index <= horizon else None


def _recalculate(base: dict[str, Any], movements: list[dict[str, Any]], scenario_id: str,
                 description: str, action_log: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild weekly cash and reserve metrics from a transformed movement ledger."""
    start = date.fromisoformat(base["forecast_start_date"])
    horizon = int(base["horizon_weeks"])
    opening = _money(base["opening_cash"])
    reserve = _money(base["minimum_cash_reserve"])
    weekly: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    current = opening
    total_receipts = ZERO
    total_payments = ZERO

    for item in movements:
        tx_date = date.fromisoformat(item["movement_date"]) if item.get("movement_date") else None
        idx = _index_for(tx_date, start, horizon) if tx_date else None
        item["week_index"] = idx
        item["outside_horizon"] = idx is None
        if idx is None:
            outside.append(item)

    outside_receipts = sum((_money(item["amount"]) for item in outside if item["direction"] == "receipt"), ZERO)
    outside_payments = sum((_money(item["amount"]) for item in outside if item["direction"] == "payment"), ZERO)

    for idx in range(1, horizon + 1):
        week_start = start + timedelta(days=(idx - 1) * 7)
        opening_week = current
        known_receipts = estimated_receipts = known_payments = estimated_payments = ZERO
        for item in movements:
            if item["week_index"] != idx:
                continue
            amount = _money(item["amount"])
            if item["direction"] == "receipt":
                if item["source_type"] == "known":
                    known_receipts += amount
                else:
                    estimated_receipts += amount
            elif item["direction"] == "payment":
                if item["source_type"] == "known":
                    known_payments += amount
                else:
                    estimated_payments += amount
            else:
                raise ScenarioEngineError(f"Unknown movement direction: {item['direction']!r}.")
        receipts = known_receipts + estimated_receipts
        payments = known_payments + estimated_payments
        closing = (opening_week + receipts - payments).quantize(CENT, rounding=ROUND_HALF_UP)
        current = closing
        total_receipts += receipts
        total_payments += payments
        weekly.append({
            "week_index": idx, "week_start_date": week_start.isoformat(),
            "opening_cash": f"{opening_week:.2f}", "known_receipts": f"{known_receipts:.2f}",
            "estimated_receipts": f"{estimated_receipts:.2f}", "known_payments": f"{known_payments:.2f}",
            "estimated_payments": f"{estimated_payments:.2f}", "total_receipts": f"{receipts:.2f}",
            "total_payments": f"{payments:.2f}", "closing_cash": f"{closing:.2f}",
            "reserve_status": "Compliant" if closing >= reserve else "Below reserve",
        })

    closings = [_money(row["closing_cash"]) for row in weekly]
    low = min(closings)
    low_week = next(row["week_index"] for row in weekly if _money(row["closing_cash"]) == low)
    breaches = [row["week_index"] for row in weekly if _money(row["closing_cash"]) < reserve]
    first_breach = breaches[0] if breaches else None
    recovery = next((row["week_index"] for row in weekly if first_breach is not None
                     and row["week_index"] > first_breach and _money(row["closing_cash"]) >= reserve), None)
    opening_below = opening < reserve
    reconciled = (opening + total_receipts - total_payments).quantize(CENT) == closings[-1]
    if not reconciled:
        raise ScenarioEngineError(f"Scenario {scenario_id} failed cash reconciliation.")
    return {
        "scenario_id": scenario_id, "description": description, "status": "Breach projected" if breaches or opening_below else "Reserve maintained",
        "currency": base["currency"], "forecast_start_date": base["forecast_start_date"], "horizon_weeks": horizon,
        "opening_cash": f"{opening:.2f}", "minimum_cash_reserve": f"{reserve:.2f}",
        "opening_cash_below_reserve": opening_below, "weeks": weekly, "movements": movements,
        "outside_horizon_movements": outside, "lowest_cash": f"{low:.2f}", "lowest_cash_week": low_week,
        "maximum_reserve_shortfall": f"{max(ZERO, reserve-low):.2f}", "first_breach_week": first_breach,
        "breach_week_count": len(breaches), "recovery_week": recovery,
        "reserve_restored_for_horizon": not breaches and not opening_below,
        "total_receipts": f"{total_receipts:.2f}", "total_payments": f"{total_payments:.2f}",
        "outside_horizon_receipts": f"{outside_receipts:.2f}", "outside_horizon_payments": f"{outside_payments:.2f}",
        "reconciliation_status": "Reconciled", "action_log": action_log,
    }


def build_scenarios(base_forecast: dict[str, Any], project_root: str | Path,
                    customer_delay_days: int = 7, supplier_deferral_days: int = 7,
                    accelerated_receipt_days: int = 7) -> dict[str, Any]:
    """Build base, customer-delay, supplier-deferral, combined and optional acceleration cases.

    Customer delay shifts only the designated known major receipt. Supplier
    deferral shifts only known payments explicitly marked deferrable=true and
    excludes protected payment categories. Deferrals change timing, not totals.
    Acceleration is a separate action scenario and is not combined by default.
    """
    for name, value in (("customer_delay_days", customer_delay_days),
                        ("supplier_deferral_days", supplier_deferral_days),
                        ("accelerated_receipt_days", accelerated_receipt_days)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 14:
            raise ScenarioEngineError(f"{name} must be an integer from 0 to 14.")
    root = Path(project_root).resolve()
    with (root / "config/forecast_config.json").open(encoding="utf-8") as handle:
        config = json.load(handle)
    major_id = config["designated_major_receipt_id"]
    base_movements = deepcopy(base_forecast["movements"])
    forecast_start = date.fromisoformat(base_forecast["forecast_start_date"])
    horizon_end = forecast_start + timedelta(days=7 * int(base_forecast["horizon_weeks"]) - 1)

    # Rule-based candidates are invoice-backed known receipts with positive
    # amounts whose original dates and accelerated dates both remain in horizon.
    # This is an illustrative assumption, not a claim of customer commitment.
    invoice_rows: dict[str, dict[str, str]] = {}
    with (root / "data/input/customer_receipts.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            invoice_rows[row["transaction_id"]] = row
    invoice_register: list[dict[str, Any]] = []
    for movement in base_movements:
        if movement.get("direction") != "receipt" or movement.get("source_type") != "known":
            continue
        movement_date = movement.get("movement_date")
        row = invoice_rows.get(movement.get("movement_id"), {})
        amount = _money(movement.get("amount", "0"))
        eligible = False
        reason = "Not eligible under the seven-day rule."
        accelerated_date = None
        if movement_date:
            original_date = date.fromisoformat(movement_date)
            candidate_date = original_date - timedelta(days=accelerated_receipt_days)
            eligible = (amount > ZERO and forecast_start <= original_date <= horizon_end
                        and forecast_start <= candidate_date <= horizon_end)
            accelerated_date = candidate_date.isoformat()
            reason = ("Illustrative candidate: positive invoice-backed receipt; original and accelerated dates remain within forecast horizon."
                      if eligible else "Excluded: amount/date does not meet the documented eligibility rule.")
        invoice_register.append({
            "invoice_reference": movement.get("movement_id"),
            "customer_id": row.get("customer_id", "Not supplied"),
            "outstanding_amount": f"{amount:.2f}",
            "original_expected_receipt_date": movement_date,
            "hypothetical_accelerated_date": accelerated_date,
            "days_brought_forward": accelerated_receipt_days if eligible else 0,
            "eligible_candidate": eligible,
            "selected_for_action": eligible,
            "confirmation_status": "Hypothetical — not confirmed",
            "eligibility_rationale": reason,
        })
    eligible_ids = {item["invoice_reference"] for item in invoice_register if item["eligible_candidate"]}

    def transform(delay_customer: int = 0, defer_suppliers: int = 0, accelerate: int = 0):
        """Copy and shift eligible dated movements without changing amounts."""
        records = deepcopy(base_movements)
        actions: list[dict[str, Any]] = []
        for item in records:
            if not item.get("movement_date"):
                continue
            tx_date = date.fromisoformat(item["movement_date"])
            delta = 0
            action_type = None
            if item["movement_id"] == major_id and item["direction"] == "receipt" and delay_customer:
                delta, action_type = delay_customer, "customer_receipt_delay"
            elif accelerate and item["direction"] == "receipt" and item["movement_id"] in eligible_ids:
                delta, action_type = -accelerate, "accelerated_receipt_action"
            elif defer_suppliers and item["direction"] == "payment" and item["source_type"] == "known":
                eligible = "deferrable=true" in item.get("description", "").lower()
                if eligible and item.get("category") not in PROTECTED:
                    delta, action_type = defer_suppliers, "supplier_payment_deferral"
            if delta:
                new_date = tx_date + timedelta(days=delta)
                item["movement_date"] = new_date.isoformat()
                item["description"] = f"{item.get('description', '')}; scenario {action_type}: {delta:+d} day(s)"
                actions.append({"movement_id": item["movement_id"], "action": action_type,
                                "original_date": tx_date.isoformat(), "scenario_date": new_date.isoformat(),
                                "amount": item["amount"], "amount_change": "0.00"})
        return records, actions

    cases = [
        ("base", "Base case", 0, 0, 0),
        ("customer_delay", f"Major customer receipt delayed {customer_delay_days} days", customer_delay_days, 0, 0),
        ("supplier_deferral", f"Eligible supplier payments deferred {supplier_deferral_days} days", 0, supplier_deferral_days, 0),
        ("combined_stress", f"Combined: customer delay {customer_delay_days} days and supplier deferral {supplier_deferral_days} days", customer_delay_days, supplier_deferral_days, 0),
        ("accelerated_receipt_action", f"Separate hypothetical action: {len(eligible_ids)} eligible invoice(s) accelerated {accelerated_receipt_days} days", 0, 0, accelerated_receipt_days),
    ]
    results = []
    for scenario_id, description, customer_days, supplier_days, acceleration_days in cases:
        records, actions = transform(customer_days, supplier_days, acceleration_days)
        results.append(_recalculate(base_forecast, records, scenario_id, description, actions))

    comparison = []
    for result in results:
        comparison.append({
            "scenario_id": result["scenario_id"], "status": result["status"],
            "lowest_cash": result["lowest_cash"], "lowest_cash_week": result["lowest_cash_week"],
            "first_breach_week": result["first_breach_week"],
            "maximum_reserve_shortfall": result["maximum_reserve_shortfall"],
            "breach_week_count": result["breach_week_count"], "recovery_week": result["recovery_week"],
            "reserve_restored_for_horizon": result["reserve_restored_for_horizon"],
            "total_receipts": result["total_receipts"], "total_payments": result["total_payments"],
            "outside_horizon_movement_count": len(result["outside_horizon_movements"]),
            "outside_horizon_receipts": result["outside_horizon_receipts"],
            "outside_horizon_payments": result["outside_horizon_payments"],
        })
    return {
        "engine_version": "stage_4_3", "invoice_register": invoice_register,
        "acceleration_rule": "Positive known invoice-backed receipts whose original and accelerated dates both fall within the 13-week forecast horizon; hypothetical only.",
        "parameters": {"customer_delay_days": customer_delay_days,
            "supplier_deferral_days": supplier_deferral_days, "accelerated_receipt_days": accelerated_receipt_days,
            "protected_payment_categories": sorted(PROTECTED)},
        "scenarios": results, "comparison": comparison,
        "notes": ["All calculations are deterministic Python calculations.",
                  "Supplier deferral changes timing, not payment amount or total payments.",
                  "Accelerated receipt is a separate hypothetical action scenario; eligible invoice candidates are listed and amounts are timing-shifted without changing total receipts.",
                  "Movements outside the 13-week horizon are disclosed and excluded from weekly totals."],
    }

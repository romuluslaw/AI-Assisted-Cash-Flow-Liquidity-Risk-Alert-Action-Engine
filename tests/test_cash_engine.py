"""Independent expected-value tests for deterministic cash calculations."""
from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.cash_engine import CashEngineError, CashMovement, _weekly_results, calculate_cash_forecast

ROOT = Path(__file__).resolve().parents[1]


def test_weekly_roll_forward_matches_independent_hand_calculation() -> None:
    """Verify cash arithmetic with a tiny hand-computed two-week ledger."""
    movements = [
        CashMovement("R1", 1, "2026-01-01", Decimal("100.00"), "receipt", "known", "Customer", "receipt"),
        CashMovement("P1", 1, "2026-01-02", Decimal("30.00"), "payment", "known", "Supplier", "payment"),
        CashMovement("P2", 2, "2026-01-09", Decimal("20.00"), "payment", "known", "Supplier", "payment"),
    ]
    weeks = _weekly_results(movements, date(2026, 1, 1), 2, Decimal("50.00"), Decimal("40.00"))
    assert weeks[0].closing_cash == Decimal("120.00")  # 50 + 100 - 30
    assert weeks[1].opening_cash == Decimal("120.00")
    assert weeks[1].closing_cash == Decimal("100.00")  # 120 - 20


def test_reserve_equality_is_compliant_and_below_reserve_is_breach() -> None:
    """The reserve rule is strict: equality is compliant, only lower is breach."""
    equal = [CashMovement("P", 1, "2026-01-01", Decimal("10.00"), "payment", "known", "X", "")]
    equal_week = _weekly_results(equal, date(2026, 1, 1), 1, Decimal("110.00"), Decimal("100.00"))[0]
    below_week = _weekly_results(equal, date(2026, 1, 1), 1, Decimal("109.99"), Decimal("100.00"))[0]
    assert equal_week.closing_cash == Decimal("100.00")
    assert equal_week.reserve_status == "Compliant"
    assert below_week.closing_cash == Decimal("99.99")
    assert below_week.reserve_status == "Breach"


def test_synthetic_forecast_has_13_reconciled_weeks_and_known_status() -> None:
    """Validate the end-to-end deterministic forecast on approved synthetic data."""
    result = calculate_cash_forecast(ROOT)
    assert len(result.weeks) == 13
    assert result.reconciliation_status == "Reconciled"
    assert result.weeks[0].opening_cash == Decimal("420000.00")
    assert result.weeks[-1].closing_cash == result.opening_cash + result.total_receipts - result.total_payments
    assert result.status in {"Reserve maintained", "Breach projected"}


def test_claims_estimate_uses_historical_claims_rate() -> None:
    """Historical claims of 3% of payroll produce 1,200 on 40,000 payroll."""
    result = calculate_cash_forecast(ROOT)
    claims = next(m for m in result.movements if m.movement_id == "EST_CLAIMS_W01")
    assert claims.amount == Decimal("1200.00")
    assert claims.direction == "payment"
    assert claims.source_type == "estimated"


def test_non_major_collection_estimates_are_separate_and_outside_horizon_is_tracked() -> None:
    """Collection shares create estimated receipts and retain late collections outside totals."""
    result = calculate_cash_forecast(ROOT)
    estimated = [m for m in result.movements if m.category == "Non-major customer collections"]
    assert estimated
    assert all(m.source_type == "estimated" for m in estimated)
    assert any(m.outside_horizon for m in estimated)
    assert any("beyond_horizon" in m.description for m in result.outside_horizon_movements)
    assert sum((w.estimated_receipts for w in result.weeks), Decimal("0.00")) < sum(
        (m.amount for m in estimated), Decimal("0.00")
    )


def test_adhoc_estimates_are_weekly_and_explain_baseline_adjustment() -> None:
    """Ad hoc estimates retain category-level baseline and scheduled-offset evidence."""
    result = calculate_cash_forecast(ROOT)
    adhoc = [m for m in result.movements if m.movement_id.startswith("EST_ADHOC_")]
    assert len(adhoc) > 0
    assert all(m.direction == "payment" and m.source_type == "estimated" for m in adhoc)
    assert all("Historical category baseline" in m.description for m in adhoc)


def test_critical_invalid_input_blocks_cash_forecast(tmp_path: Path) -> None:
    """The engine must not calculate a definitive forecast when input contracts fail."""
    copied = tmp_path / "project"
    shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"))
    config_path = copied / "config/forecast_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["horizon_weeks"] = 12
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    with pytest.raises(CashEngineError, match="Input validation blocked"):
        calculate_cash_forecast(copied)


def test_forecast_payroll_is_included_as_cash_outflow() -> None:
    """Forecast payroll must be included separately from estimated staff claims."""
    result = calculate_cash_forecast(ROOT)
    payroll = next(m for m in result.movements if m.movement_id == "EST_PAYROLL_W01")
    claims = next(m for m in result.movements if m.movement_id == "EST_CLAIMS_W01")
    assert payroll.amount == Decimal("40000.00")
    assert payroll.category == "Payroll"
    assert claims.amount == Decimal("1200.00")
    assert payroll.amount != claims.amount


def test_scheduled_payroll_offsets_forecast_payroll_to_prevent_double_counting(tmp_path: Path) -> None:
    """A known payroll payment reduces the estimated payroll remainder in that week."""
    copied = tmp_path / "project"
    shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"))
    payment_path = copied / "data/input/known_payments.csv"
    with payment_path.open("a", encoding="utf-8") as handle:
        handle.write("PAY_PAYROLL_TEST,Payroll,2026-10-15,10000.00,false\n")
    result = calculate_cash_forecast(copied)
    payroll = next(m for m in result.movements if m.movement_id == "EST_PAYROLL_W01")
    known_payroll = next(m for m in result.movements if m.movement_id == "PAY_PAYROLL_TEST")
    assert known_payroll.amount == Decimal("10000.00")
    assert payroll.amount == Decimal("30000.00")


def test_collection_estimates_reconcile_to_total_sales_cohorts() -> None:
    """All collection buckets, including outside-horizon amounts, reconcile to sales."""
    import csv

    with (ROOT / "data/input/forecast_non_major_sales.csv").open(newline="", encoding="utf-8-sig") as handle:
        total_sales = sum((Decimal(row["forecast_sales"]) for row in csv.DictReader(handle)), Decimal("0.00"))
    result = calculate_cash_forecast(ROOT)
    collection_amount = sum(
        (m.amount for m in result.movements if m.category == "Non-major customer collections"),
        Decimal("0.00"),
    )
    assert collection_amount == total_sales


def test_opening_cash_below_reserve_is_flagged_separately(tmp_path: Path) -> None:
    """Opening cash risk is reported even if weekly closing balances later recover."""
    copied = tmp_path / "project"
    shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"))
    config_path = copied / "config/forecast_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["opening_cash"] = 100000.00
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    result = calculate_cash_forecast(copied)
    assert result.opening_cash_below_reserve is True
    assert result.status == "Breach projected"
    assert any("Opening cash is already below" in warning for warning in result.warnings)

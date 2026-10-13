"""Automated acceptance tests for the initial input-contract layer."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from src.input_validation import validate_project_inputs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    """Create an isolated project copy so mutation tests never alter source data."""
    target = tmp_path / "project"
    shutil.copytree(PROJECT_ROOT / "config", target / "config")
    shutil.copytree(PROJECT_ROOT / "data", target / "data")
    return target


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Load a CSV while retaining its original column order for controlled edits."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_rows(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    """Write modified test data without changing the test fixture's schema."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in columns} for row in rows])


def test_synthetic_input_package_passes_contract_validation() -> None:
    """The supplied complete synthetic dataset should pass with no warnings."""
    report = validate_project_inputs(PROJECT_ROOT)
    assert report.overall_status == "Valid"
    assert report.files_checked
    assert report.issues[0].status == "Valid"


def test_missing_required_receipt_column_blocks_package(tmp_path: Path) -> None:
    """A missing required field must block rather than be guessed or defaulted."""
    root = _copy_project(tmp_path)
    path = root / "data/input/customer_receipts.csv"
    columns, rows = _read_rows(path)
    columns.remove("amount")
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "required_columns" for issue in report.issues)


def test_negative_receipt_amount_blocks_package(tmp_path: Path) -> None:
    """Negative input amounts are invalid because direction comes from the file type."""
    root = _copy_project(tmp_path)
    path = root / "data/input/customer_receipts.csv"
    columns, rows = _read_rows(path)
    rows[0]["amount"] = "-100.00"
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "amount" and issue.file_name == path.name for issue in report.issues)


def test_duplicate_transaction_id_blocks_package(tmp_path: Path) -> None:
    """Duplicate IDs make movement-level traceability ambiguous and must block."""
    root = _copy_project(tmp_path)
    path = root / "data/input/customer_receipts.csv"
    columns, rows = _read_rows(path)
    rows[1]["transaction_id"] = rows[0]["transaction_id"]
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "unique_transaction_id" for issue in report.issues)


def test_collection_shares_must_reconcile_to_one_hundred_percent(tmp_path: Path) -> None:
    """Collection timing buckets must include all shares, including beyond-horizon."""
    root = _copy_project(tmp_path)
    path = root / "config/collection_assumptions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["timing_buckets"][0]["collection_share"] = 0.49
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "shares_reconcile_to_100_percent" for issue in report.issues)


def test_protected_payment_cannot_be_marked_deferrable(tmp_path: Path) -> None:
    """Protected payment categories must not become eligible through a flag error."""
    root = _copy_project(tmp_path)
    path = root / "data/input/known_payments.csv"
    columns, rows = _read_rows(path)
    rows[4]["deferrable"] = "true"  # Taxes is protected in the synthetic input.
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "protected_payment_not_deferrable" for issue in report.issues)


def test_forecast_inputs_must_cover_exactly_thirteen_weeks(tmp_path: Path) -> None:
    """A missing forecast week blocks the affected input package."""
    root = _copy_project(tmp_path)
    path = root / "data/input/forecast_payroll.csv"
    columns, rows = _read_rows(path)
    _write_rows(path, columns, rows[:-1])
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "complete_forecast_horizon" and issue.file_name == path.name for issue in report.issues)


def test_thirteen_weeks_of_history_is_minimum_and_twenty_six_is_preferred(tmp_path: Path) -> None:
    """Thirteen historical weeks produces a warning; fewer than thirteen blocks."""
    root = _copy_project(tmp_path)
    path = root / "data/input/historical_adhoc_payments.csv"
    columns, rows = _read_rows(path)
    first_13_weeks = rows[:13 * 3]
    _write_rows(path, columns, first_13_weeks)
    report = validate_project_inputs(root)
    assert report.overall_status == "Warning"
    assert any(issue.field_or_rule == "preferred_history_26_weeks" for issue in report.issues)

    _write_rows(path, columns, rows[:12 * 3])
    blocked = validate_project_inputs(root)
    assert blocked.overall_status == "Blocked"
    assert any(issue.field_or_rule == "minimum_history_13_weeks" for issue in blocked.issues)


def test_zero_payroll_reference_blocks_claims_rate(tmp_path: Path) -> None:
    """A zero denominator must not be allowed to produce a claims rate."""
    root = _copy_project(tmp_path)
    path = root / "data/input/historical_claims_payroll.csv"
    columns, rows = _read_rows(path)
    rows[0]["payroll_amount"] = "0"
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "payroll_amount" for issue in report.issues)


def test_out_of_horizon_receipt_is_warned_not_silently_discarded(tmp_path: Path) -> None:
    """Beyond-horizon movements remain in source data and are explicitly flagged."""
    root = _copy_project(tmp_path)
    path = root / "data/input/customer_receipts.csv"
    columns, rows = _read_rows(path)
    rows[1]["expected_date"] = "2027-02-01"
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Warning"
    assert any(issue.field_or_rule == "movement_outside_forecast_horizon" for issue in report.issues)
    assert len(_read_rows(path)[1]) == len(rows)


def test_major_receipt_must_match_configured_designated_ids(tmp_path: Path) -> None:
    """The stress test must target the exact receipt and customer approved in config."""
    root = _copy_project(tmp_path)
    path = root / "data/input/customer_receipts.csv"
    columns, rows = _read_rows(path)
    rows[0]["transaction_id"] = "RCPT_WRONG_TARGET"
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "designated_major_receipt_matches_config" for issue in report.issues)


def test_receipt_and_payment_streams_cannot_share_transaction_id(tmp_path: Path) -> None:
    """Cross-stream duplicate IDs must block to preserve movement traceability."""
    root = _copy_project(tmp_path)
    receipt_path = root / "data/input/customer_receipts.csv"
    payment_path = root / "data/input/known_payments.csv"
    _, receipts = _read_rows(receipt_path)
    payment_columns, payments = _read_rows(payment_path)
    payments[0]["transaction_id"] = receipts[0]["transaction_id"]
    _write_rows(payment_path, payment_columns, payments)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "cross_stream_unique_ids" for issue in report.issues)


def test_invalid_transaction_date_blocks_package(tmp_path: Path) -> None:
    """Unparseable dates must be corrected rather than dropped from the forecast."""
    root = _copy_project(tmp_path)
    path = root / "data/input/known_payments.csv"
    columns, rows = _read_rows(path)
    rows[0]["expected_date"] = "not-a-date"
    _write_rows(path, columns, rows)
    report = validate_project_inputs(root)
    assert report.overall_status == "Blocked"
    assert any(issue.field_or_rule == "expected_date" for issue in report.issues)

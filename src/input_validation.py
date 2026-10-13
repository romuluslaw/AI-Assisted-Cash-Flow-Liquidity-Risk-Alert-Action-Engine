"""Input contracts and validation controls for Project 05.

This module intentionally uses Python's standard library only. Validation is a
control layer: it checks whether an input can safely be used; it does not make
financial estimates or calculate cash forecasts.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

VALID_STATUSES = {"Valid", "Warning", "Blocked"}


@dataclass(frozen=True)
class ValidationIssue:
    """One traceable validation finding.

    Attributes:
        status: Valid, Warning, or Blocked severity.
        file_name: Input file that triggered the finding.
        field_or_rule: Field name or business rule being checked.
        message: Human-readable explanation of the result.
        correction: Suggested correction when the finding is not Valid.
        component: Forecast component potentially affected by the finding.
    """

    status: str
    file_name: str
    field_or_rule: str
    message: str
    correction: str = ""
    component: str = "input"


@dataclass
class ValidationReport:
    """Machine-readable validation result for the full input package."""

    overall_status: str = "Valid"
    issues: list[ValidationIssue] = field(default_factory=list)
    files_checked: list[str] = field(default_factory=list)

    def add(self, issue: ValidationIssue) -> None:
        """Add an issue and elevate overall status to the most severe level."""
        self.issues.append(issue)
        rank = {"Valid": 0, "Warning": 1, "Blocked": 2}
        if rank[issue.status] > rank[self.overall_status]:
            self.overall_status = issue.status

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable report for logs and future UI display."""
        return {
            "overall_status": self.overall_status,
            "files_checked": self.files_checked,
            "issues": [asdict(issue) for issue in self.issues],
        }


REQUIRED_COLUMNS: dict[str, set[str]] = {
    "customer_receipts.csv": {
        "transaction_id", "customer_id", "expected_date", "amount", "is_major_stress_target"
    },
    "known_payments.csv": {
        "transaction_id", "category", "expected_date", "amount", "deferrable"
    },
    "historical_claims_payroll.csv": {
        "reference_start_date", "reference_end_date", "claims_paid_amount", "payroll_amount"
    },
    "forecast_payroll.csv": {"week_index", "week_start_date", "forecast_payroll"},
    "forecast_non_major_sales.csv": {"week_index", "week_start_date", "forecast_sales"},
    "historical_adhoc_payments.csv": {
        "transaction_id", "payment_date", "category", "amount"
    },
}


def _load_json(path: Path, report: ValidationReport) -> dict[str, Any] | None:
    """Read a JSON object and report syntax or top-level-shape failures."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        report.add(ValidationIssue(
            "Blocked", path.name, "file_readable_json", f"Cannot read valid JSON: {exc}",
            "Restore the file as valid UTF-8 JSON.", "configuration"
        ))
        return None
    if not isinstance(value, dict):
        report.add(ValidationIssue(
            "Blocked", path.name, "top_level_object", "The JSON top level must be an object.",
            "Provide a JSON object containing the required configuration fields.", "configuration"
        ))
        return None
    return value


def _read_csv(path: Path, required_columns: set[str], report: ValidationReport) -> list[dict[str, str]] | None:
    """Read a CSV and check required headers before any row-level validation."""
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            missing = sorted(required_columns - headers)
            if missing:
                report.add(ValidationIssue(
                    "Blocked", path.name, "required_columns",
                    f"Missing required columns: {', '.join(missing)}.",
                    "Restore the required column names exactly as documented.", path.stem
                ))
                return None
            rows = list(reader)
    except OSError as exc:
        report.add(ValidationIssue(
            "Blocked", path.name, "file_readable_csv", f"Cannot read CSV: {exc}",
            "Restore the input file at the documented path.", path.stem
        ))
        return None
    if not rows:
        report.add(ValidationIssue(
            "Blocked", path.name, "non_empty_file", "The CSV contains a header but no data rows.",
            "Provide the required input records; do not use an empty file to imply zero.", path.stem
        ))
    return rows


def _parse_date(value: str, file_name: str, field_name: str, row_number: int,
                report: ValidationReport, component: str) -> date | None:
    """Parse an ISO date and report a row-specific blocking issue on failure."""
    try:
        return date.fromisoformat(value.strip())
    except (TypeError, ValueError):
        report.add(ValidationIssue(
            "Blocked", file_name, field_name,
            f"Row {row_number}: {value!r} is not a valid YYYY-MM-DD date.",
            "Correct the date using YYYY-MM-DD format.", component
        ))
        return None


def _parse_amount(value: str, file_name: str, field_name: str, row_number: int,
                  report: ValidationReport, component: str, *, allow_zero: bool = True) -> float | None:
    """Parse a finite non-negative amount, preserving explicit zero as valid."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = float("nan")
    if amount != amount or amount in (float("inf"), float("-inf")) or amount < 0 or (not allow_zero and amount == 0):
        requirement = "positive" if not allow_zero else "non-negative"
        report.add(ValidationIssue(
            "Blocked", file_name, field_name,
            f"Row {row_number}: amount {value!r} must be finite and {requirement}.",
            "Correct the amount; missing or invalid values must not be replaced silently with zero.", component
        ))
        return None
    return amount


def _parse_bool(value: str, file_name: str, field_name: str, row_number: int,
                report: ValidationReport, component: str) -> bool | None:
    """Accept explicit true/false values only; ambiguous flags block validation."""
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    report.add(ValidationIssue(
        "Blocked", file_name, field_name,
        f"Row {row_number}: {value!r} is not an explicit true/false value.",
        "Use true or false; do not leave control flags blank.", component
    ))
    return None


def _validate_unique_ids(rows: list[dict[str, str]], file_name: str,
                         report: ValidationReport, component: str) -> None:
    """Block duplicate or blank transaction IDs within an input stream."""
    seen: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        identifier = (row.get("transaction_id") or "").strip()
        if not identifier:
            report.add(ValidationIssue(
                "Blocked", file_name, "transaction_id", f"Row {row_number}: transaction ID is blank.",
                "Assign a stable, non-blank unique transaction ID.", component
            ))
        elif identifier in seen:
            report.add(ValidationIssue(
                "Blocked", file_name, "unique_transaction_id",
                f"Row {row_number}: duplicate transaction ID {identifier!r}.",
                "Remove the duplicate or assign the correct unique transaction ID.", component
            ))
        seen.add(identifier)


def _check_required_config(config: dict[str, Any], report: ValidationReport) -> None:
    """Validate required forecast settings and their business constraints."""
    required = {
        "forecast_start_date", "opening_cash", "minimum_cash_reserve", "currency", "horizon_weeks"
    }
    missing = sorted(required - config.keys())
    if missing:
        report.add(ValidationIssue(
            "Blocked", "forecast_config.json", "required_settings",
            f"Missing required settings: {', '.join(missing)}.",
            "Restore all required settings before forecasting.", "configuration"
        ))
        return
    try:
        start_date = date.fromisoformat(str(config["forecast_start_date"]))
    except ValueError:
        start_date = None
        report.add(ValidationIssue(
            "Blocked", "forecast_config.json", "forecast_start_date",
            "Forecast start date must use YYYY-MM-DD.", "Provide a valid ISO date.", "configuration"
        ))
    for field_name in ("opening_cash", "minimum_cash_reserve"):
        _parse_amount(str(config[field_name]), "forecast_config.json", field_name, 1,
                      report, "configuration")
    if not isinstance(config["horizon_weeks"], int) or isinstance(config["horizon_weeks"], bool) or config["horizon_weeks"] != 13:
        report.add(ValidationIssue(
            "Blocked", "forecast_config.json", "horizon_weeks",
            "The approved MVP horizon must be exactly 13 weeks.",
            "Set horizon_weeks to 13.", "configuration"
        ))
    if not isinstance(config["currency"], str) or not config["currency"].strip():
        report.add(ValidationIssue(
            "Blocked", "forecast_config.json", "currency", "Currency must be a non-blank code.",
            "Provide a currency code such as SGD.", "configuration"
        ))
    if start_date and start_date.weekday() != 0:
        report.add(ValidationIssue(
            "Warning", "forecast_config.json", "forecast_start_date_week_start",
            "Forecast start date is not a Monday; confirm the intended weekly convention.",
            "Use Monday week starts or explicitly document a different convention.", "configuration"
        ))
    protected = config.get("protected_payment_categories", [])
    if not isinstance(protected, list) or any(not isinstance(item, str) or not item.strip() for item in protected):
        report.add(ValidationIssue(
            "Blocked", "forecast_config.json", "protected_payment_categories",
            "Protected payment categories must be a list of non-blank names.",
            "Provide a list of protected category names.", "configuration"
        ))


def validate_project_inputs(project_root: str | Path) -> ValidationReport:
    """Validate the configured files and return an auditable status report.

    A missing/invalid critical contract blocks the affected input package. Data
    dates outside the 13-week window are warnings because the approved design
    requires them to remain visible as beyond-horizon items, not be discarded.
    This function does not calculate cash balances or fill missing data.
    """
    root = Path(project_root)
    config_dir = root / "config"
    input_dir = root / "data" / "input"
    report = ValidationReport()

    config_path = config_dir / "forecast_config.json"
    collection_path = config_dir / "collection_assumptions.json"
    config = _load_json(config_path, report) if config_path.exists() else None
    if not config_path.exists():
        report.add(ValidationIssue("Blocked", config_path.name, "file_exists", "Required configuration file is missing.", "Restore the file.", "configuration"))
    if config is not None:
        _check_required_config(config, report)
        report.files_checked.append(config_path.name)

    collection = _load_json(collection_path, report) if collection_path.exists() else None
    if not collection_path.exists():
        report.add(ValidationIssue("Blocked", collection_path.name, "file_exists", "Required collection assumptions file is missing.", "Restore the file.", "collection_assumptions"))
    if collection is not None:
        report.files_checked.append(collection_path.name)
        buckets = collection.get("timing_buckets")
        if not isinstance(buckets, list) or not buckets:
            report.add(ValidationIssue("Blocked", collection_path.name, "timing_buckets", "At least one timing bucket is required.", "Define collection timing buckets.", "collection_assumptions"))
        else:
            shares: list[float] = []
            for index, bucket in enumerate(buckets, start=1):
                if not isinstance(bucket, dict) or "collection_share" not in bucket:
                    report.add(ValidationIssue("Blocked", collection_path.name, "collection_share", f"Bucket {index} is missing a collection share.", "Provide a share between 0 and 1 for every bucket.", "collection_assumptions"))
                    continue
                try:
                    share = float(bucket["collection_share"])
                except (TypeError, ValueError):
                    share = -1
                if not 0 <= share <= 1:
                    report.add(ValidationIssue("Blocked", collection_path.name, "collection_share", f"Bucket {index} share must be between 0 and 1.", "Correct the share.", "collection_assumptions"))
                else:
                    shares.append(share)
            tolerance = collection.get("share_tolerance", 0.000001)
            try:
                tolerance = float(tolerance)
            except (TypeError, ValueError):
                tolerance = 0.000001
            if shares and abs(sum(shares) - 1.0) > tolerance:
                report.add(ValidationIssue(
                    "Blocked", collection_path.name, "shares_reconcile_to_100_percent",
                    f"Collection shares sum to {sum(shares):.6f}, not 1.000000.",
                    "Adjust timing-bucket shares so they sum to 100%, including beyond-horizon collections.", "collection_assumptions"
                ))

    all_rows: dict[str, list[dict[str, str]] | None] = {}
    for file_name, columns in REQUIRED_COLUMNS.items():
        path = input_dir / file_name
        if not path.exists():
            report.add(ValidationIssue("Blocked", file_name, "file_exists", "Required input file is missing.", "Restore the file using the documented schema.", file_name.removesuffix(".csv")))
            all_rows[file_name] = None
            continue
        rows = _read_csv(path, columns, report)
        all_rows[file_name] = rows
        report.files_checked.append(file_name)

    # Receipt records: validate IDs, dates, positive/non-negative amounts and flags.
    receipts = all_rows.get("customer_receipts.csv")
    if receipts:
        _validate_unique_ids(receipts, "customer_receipts.csv", report, "customer_receipts")
        for row_number, row in enumerate(receipts, start=2):
            _parse_date(row.get("expected_date", ""), "customer_receipts.csv", "expected_date", row_number, report, "customer_receipts")
            _parse_amount(row.get("amount", ""), "customer_receipts.csv", "amount", row_number, report, "customer_receipts")
            _parse_bool(row.get("is_major_stress_target", ""), "customer_receipts.csv", "is_major_stress_target", row_number, report, "customer_receipts")
            if not (row.get("customer_id") or "").strip():
                report.add(ValidationIssue("Blocked", "customer_receipts.csv", "customer_id", f"Row {row_number}: customer ID is blank.", "Provide a stable customer ID.", "customer_receipts"))

    # Payment records: protect payroll, tax, debt and statutory categories from contradictory deferral flags.
    payments = all_rows.get("known_payments.csv")
    if payments:
        _validate_unique_ids(payments, "known_payments.csv", report, "known_payments")
        protected = {str(x).strip().casefold() for x in (config or {}).get("protected_payment_categories", [])}
        for row_number, row in enumerate(payments, start=2):
            _parse_date(row.get("expected_date", ""), "known_payments.csv", "expected_date", row_number, report, "known_payments")
            _parse_amount(row.get("amount", ""), "known_payments.csv", "amount", row_number, report, "known_payments")
            deferrable = _parse_bool(row.get("deferrable", ""), "known_payments.csv", "deferrable", row_number, report, "known_payments")
            category = (row.get("category") or "").strip()
            if not category:
                report.add(ValidationIssue("Blocked", "known_payments.csv", "category", f"Row {row_number}: category is blank.", "Provide a payment category.", "known_payments"))
            if deferrable is True and category.casefold() in protected:
                report.add(ValidationIssue(
                    "Blocked", "known_payments.csv", "protected_payment_not_deferrable",
                    f"Row {row_number}: protected category {category!r} is marked deferrable.",
                    "Set deferrable to false or correct the category only if the source record is wrong.", "known_payments"
                ))

    # Exactly one receipt must be designated for the approved major-customer stress test.
    if receipts is not None and config is not None:
        flagged = [row for row in receipts if (row.get("is_major_stress_target") or "").strip().lower() in {"true", "yes", "1"}]
        expected_receipt_id = str(config.get("designated_major_receipt_id", "")).strip()
        expected_customer_id = str(config.get("designated_major_customer_id", "")).strip()
        if len(flagged) != 1:
            report.add(ValidationIssue(
                "Blocked", "customer_receipts.csv", "unique_major_stress_target",
                f"Expected exactly one designated major receipt; found {len(flagged)}.",
                "Mark exactly one invoice-backed receipt as the major stress target.", "customer_delay_scenario"
            ))
        elif flagged[0].get("transaction_id", "").strip() != expected_receipt_id or flagged[0].get("customer_id", "").strip() != expected_customer_id:
            report.add(ValidationIssue(
                "Blocked", "customer_receipts.csv", "designated_major_receipt_matches_config",
                "The flagged major receipt does not match the receipt and customer IDs in forecast_config.json.",
                "Align the designated receipt/customer IDs or correct the source transaction flag.", "customer_delay_scenario"
            ))

    # Transaction IDs must not collide between receipt and payment streams.
    if receipts and payments:
        receipt_ids = {row.get("transaction_id", "").strip() for row in receipts}
        payment_ids = {row.get("transaction_id", "").strip() for row in payments}
        overlap = sorted((receipt_ids & payment_ids) - {""})
        if overlap:
            report.add(ValidationIssue(
                "Blocked", "customer_receipts.csv / known_payments.csv", "cross_stream_unique_ids",
                f"Transaction IDs appear in both receipt and payment streams: {', '.join(overlap)}.",
                "Assign distinct transaction IDs and verify that the same movement is not double-counted.", "cash_movements"
            ))

    # Claims reference period and payroll basis must be valid and positive.
    claims = all_rows.get("historical_claims_payroll.csv")
    if claims:
        if len(claims) != 1:
            report.add(ValidationIssue("Blocked", "historical_claims_payroll.csv", "single_reference_period", "Exactly one consistent claims/payroll reference-period row is required in the MVP.", "Provide one aggregated reference-period row with aligned claims and payroll bases.", "staff_claims"))
        for row_number, row in enumerate(claims, start=2):
            start = _parse_date(row.get("reference_start_date", ""), "historical_claims_payroll.csv", "reference_start_date", row_number, report, "staff_claims")
            end = _parse_date(row.get("reference_end_date", ""), "historical_claims_payroll.csv", "reference_end_date", row_number, report, "staff_claims")
            claims_amount = _parse_amount(row.get("claims_paid_amount", ""), "historical_claims_payroll.csv", "claims_paid_amount", row_number, report, "staff_claims")
            payroll_amount = _parse_amount(row.get("payroll_amount", ""), "historical_claims_payroll.csv", "payroll_amount", row_number, report, "staff_claims", allow_zero=False)
            if start and end and end < start:
                report.add(ValidationIssue("Blocked", "historical_claims_payroll.csv", "reference_period_order", "Reference end date precedes start date.", "Correct the reference period.", "staff_claims"))
            if claims_amount is not None and payroll_amount is not None and claims_amount > payroll_amount:
                report.add(ValidationIssue("Warning", "historical_claims_payroll.csv", "claims_to_payroll_reasonableness", "Claims paid exceed the reference-period payroll amount; confirm the basis and units.", "Confirm that claims and payroll use consistent periods and currency units.", "staff_claims"))

    # Forecast payroll and sales must each cover the exact 13-week horizon.
    forecast_start = None
    if config:
        try:
            forecast_start = date.fromisoformat(str(config.get("forecast_start_date", "")))
        except ValueError:
            pass
    expected_horizon = int((config or {}).get("horizon_weeks", 13)) if isinstance((config or {}).get("horizon_weeks", 13), int) else 13
    for file_name, amount_column in (("forecast_payroll.csv", "forecast_payroll"), ("forecast_non_major_sales.csv", "forecast_sales")):
        rows = all_rows.get(file_name)
        if not rows:
            continue
        indexes: list[int] = []
        seen_dates: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            try:
                index = int(row.get("week_index", ""))
            except (TypeError, ValueError):
                index = -1
            indexes.append(index)
            week_date = _parse_date(row.get("week_start_date", ""), file_name, "week_start_date", row_number, report, file_name.removesuffix(".csv"))
            _parse_amount(row.get(amount_column, ""), file_name, amount_column, row_number, report, file_name.removesuffix(".csv"))
            date_text = (row.get("week_start_date") or "").strip()
            if date_text in seen_dates:
                report.add(ValidationIssue("Blocked", file_name, "unique_week_start_date", f"Row {row_number}: duplicate week start date {date_text!r}.", "Provide one row per forecast week.", file_name.removesuffix(".csv")))
            seen_dates.add(date_text)
            if index < 1 or index > expected_horizon:
                report.add(ValidationIssue("Blocked", file_name, "week_index_range", f"Row {row_number}: week_index must be between 1 and {expected_horizon}.", "Correct the forecast week index.", file_name.removesuffix(".csv")))
            if forecast_start and week_date and week_date != forecast_start + timedelta(weeks=index - 1):
                report.add(ValidationIssue("Blocked", file_name, "week_date_matches_index", f"Row {row_number}: week date does not match configured forecast start and week index.", "Align week_start_date with forecast_start_date and week_index.", file_name.removesuffix(".csv")))
        if len(rows) != expected_horizon or sorted(indexes) != list(range(1, expected_horizon + 1)):
            report.add(ValidationIssue(
                "Blocked", file_name, "complete_forecast_horizon",
                f"Expected exactly {expected_horizon} unique forecast weeks; found {len(rows)} rows and indexes {sorted(indexes)}.",
                f"Provide exactly weeks 1 through {expected_horizon}.", file_name.removesuffix(".csv")
            ))

    # Historical ad hoc baseline requires 13 weeks; 26 weeks is preferred.
    history = all_rows.get("historical_adhoc_payments.csv")
    if history:
        _validate_unique_ids(history, "historical_adhoc_payments.csv", report, "historical_adhoc_payments")
        dates: list[date] = []
        for row_number, row in enumerate(history, start=2):
            payment_date = _parse_date(row.get("payment_date", ""), "historical_adhoc_payments.csv", "payment_date", row_number, report, "historical_adhoc_payments")
            if payment_date:
                dates.append(payment_date)
            _parse_amount(row.get("amount", ""), "historical_adhoc_payments.csv", "amount", row_number, report, "historical_adhoc_payments")
            if not (row.get("category") or "").strip():
                report.add(ValidationIssue("Blocked", "historical_adhoc_payments.csv", "category", f"Row {row_number}: category is blank.", "Provide a payment category.", "historical_adhoc_payments"))
        if dates:
            # Coverage is based on the number of distinct calendar weeks represented, not row count.
            distinct_weeks = {d.isocalendar()[:2] for d in dates}
            week_count = len(distinct_weeks)
            if week_count < 13:
                report.add(ValidationIssue(
                    "Blocked", "historical_adhoc_payments.csv", "minimum_history_13_weeks",
                    f"Only {week_count} distinct historical weeks are represented; at least 13 are required.",
                    "Supply at least 13 weeks of usable history; do not generate an estimate from shorter history.", "ad_hoc_baseline"
                ))
            elif week_count < 26:
                report.add(ValidationIssue(
                    "Warning", "historical_adhoc_payments.csv", "preferred_history_26_weeks",
                    f"Only {week_count} distinct historical weeks are represented; 26 weeks is preferred.",
                    "Use 26 weeks where available, or disclose the limitation of a shorter baseline.", "ad_hoc_baseline"
                ))

    # Forecast-intended movements outside the horizon are warnings, not discarded records.
    if forecast_start:
        horizon_end = forecast_start + timedelta(weeks=expected_horizon)
        for file_name, date_field, rows in (
            ("customer_receipts.csv", "expected_date", receipts),
            ("known_payments.csv", "expected_date", payments),
        ):
            if not rows:
                continue
            for row_number, row in enumerate(rows, start=2):
                try:
                    movement_date = date.fromisoformat(row.get(date_field, "").strip())
                except ValueError:
                    continue  # The row-level parser has already reported this error.
                if movement_date < forecast_start or movement_date >= horizon_end:
                    report.add(ValidationIssue(
                        "Warning", file_name, "movement_outside_forecast_horizon",
                        f"Row {row_number}: movement date {movement_date.isoformat()} is outside the 13-week forecast window and must remain visible outside the forecast total.",
                        "Confirm the date and ensure the movement is disclosed outside the 13-week cash total.", file_name.removesuffix(".csv")
                    ))

    # Explicit valid issue makes the report useful even when there are no exceptions.
    if not report.issues:
        report.add(ValidationIssue("Valid", "all_inputs", "input_contracts", "All required input contracts passed validation.", "", "input"))
    return report

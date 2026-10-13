"""Generate the deterministic, fictional input files used by Project 05.

All amounts and counterparties are synthetic. Re-running this script recreates
only the input CSVs; it does not alter source code, configuration, or outputs.
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input"
CONFIG_DIR = ROOT / "config"


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    """Write rows in a stable column order for reproducible diffs and tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def generate_inputs() -> None:
    """Create the synthetic 13-week forecast and 26-week payment history."""
    with (CONFIG_DIR / "forecast_config.json").open(encoding="utf-8") as handle:
        config = json.load(handle)
    forecast_start = date.fromisoformat(config["forecast_start_date"])

    receipts: list[dict[str, object]] = []
    # One identified large receipt is the only receipt changed by the delay scenario.
    receipts.append({
        "transaction_id": "RCPT_MAJOR_001", "customer_id": "CUST_MAJOR_001",
        "expected_date": (forecast_start + timedelta(weeks=3, days=2)).isoformat(),
        "amount": "280000.00", "is_major_stress_target": "true"
    })
    # Smaller invoice-backed receipts are separate from future-sales estimates.
    for week, amount in [(1, 28000), (2, 22000), (3, 30000), (5, 26000), (7, 24000), (9, 32000), (11, 27000), (13, 25000)]:
        receipts.append({
            "transaction_id": f"RCPT_KNOWN_{week:02d}", "customer_id": f"CUST_{(week % 4) + 1:03d}",
            "expected_date": (forecast_start + timedelta(weeks=week - 1, days=2)).isoformat(),
            "amount": f"{amount:.2f}", "is_major_stress_target": "false"
        })
    _write_csv(INPUT_DIR / "customer_receipts.csv",
               ["transaction_id", "customer_id", "expected_date", "amount", "is_major_stress_target"], receipts)

    payment_specs = [
        ("PAY_RENT_001", "Rent", 1, 18000, False),
        ("PAY_SUPPLIER_001", "Supplier", 2, 42000, True),
        ("PAY_SUPPLIER_MAJOR_001", "Supplier", 4, 205000, True),
        ("PAY_SUPPLIER_003", "Supplier", 5, 48000, True),
        ("PAY_TAX_001", "Taxes", 6, 22000, False),
        ("PAY_DEBT_001", "Debt Repayment", 7, 16000, False),
        ("PAY_SUPPLIER_004", "Supplier", 8, 56000, True),
        ("PAY_INSURANCE_001", "Insurance", 9, 12000, False),
        ("PAY_SUPPLIER_005", "Supplier", 11, 62000, True),
        ("PAY_STATUTORY_001", "Statutory Dues", 12, 9000, False),
    ]
    payments = [{
        "transaction_id": transaction_id, "category": category,
        "expected_date": (forecast_start + timedelta(weeks=week - 1, days=3)).isoformat(),
        "amount": f"{amount:.2f}", "deferrable": str(deferrable).lower()
    } for transaction_id, category, week, amount, deferrable in payment_specs]
    _write_csv(INPUT_DIR / "known_payments.csv",
               ["transaction_id", "category", "expected_date", "amount", "deferrable"], payments)

    claims = [{
        "reference_start_date": (forecast_start - timedelta(weeks=26)).isoformat(),
        "reference_end_date": (forecast_start - timedelta(days=7)).isoformat(),
        "claims_paid_amount": "36000.00", "payroll_amount": "1200000.00"
    }]
    _write_csv(INPUT_DIR / "historical_claims_payroll.csv",
               ["reference_start_date", "reference_end_date", "claims_paid_amount", "payroll_amount"], claims)

    payroll_rows = []
    sales_rows = []
    for week in range(1, 14):
        week_date = forecast_start + timedelta(weeks=week - 1)
        # Modest variability is explicit synthetic input, not a separate sales forecast engine.
        payroll = 40000 + (2000 if week in {4, 8, 12} else 0)
        sales = 80000 + (10000 if week in {3, 7, 11} else 0) - (5000 if week in {5, 9} else 0)
        payroll_rows.append({"week_index": week, "week_start_date": week_date.isoformat(), "forecast_payroll": f"{payroll:.2f}"})
        sales_rows.append({"week_index": week, "week_start_date": week_date.isoformat(), "forecast_sales": f"{sales:.2f}"})
    _write_csv(INPUT_DIR / "forecast_payroll.csv", ["week_index", "week_start_date", "forecast_payroll"], payroll_rows)
    _write_csv(INPUT_DIR / "forecast_non_major_sales.csv", ["week_index", "week_start_date", "forecast_sales"], sales_rows)

    # Twenty-six distinct historical weeks, with repeatable category-level payments.
    history_rows: list[dict[str, object]] = []
    history_start = forecast_start - timedelta(weeks=26)
    historical_categories = {
        "Office Operations": 7800,
        "Repairs & Maintenance": 3600,
        "Travel & Transport": 1900,
    }
    for week in range(26):
        week_date = history_start + timedelta(weeks=week)
        for category, base_amount in historical_categories.items():
            # Deterministic variation preserves a realistic-looking sample without randomness.
            adjustment = ((week % 5) - 2) * 125
            history_rows.append({
                "transaction_id": f"ADHOC_HIST_{week + 1:02d}_{category.split()[0].upper()}",
                "payment_date": (week_date + timedelta(days=3)).isoformat(),
                "category": category,
                "amount": f"{max(0, base_amount + adjustment):.2f}"
            })
    _write_csv(INPUT_DIR / "historical_adhoc_payments.csv",
               ["transaction_id", "payment_date", "category", "amount"], history_rows)


if __name__ == "__main__":
    generate_inputs()
    print(f"Synthetic inputs generated in {INPUT_DIR}")

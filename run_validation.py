"""Run the input contract checks and write a machine-readable report."""

from __future__ import annotations

import json
from pathlib import Path

from src.input_validation import validate_project_inputs


ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Validate all configured inputs, persist the report, and return process status."""
    report = validate_project_inputs(ROOT)
    output_path = ROOT / "outputs" / "validation_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Input validation status: {report.overall_status}")
    print(f"Files checked: {len(report.files_checked)}")
    print(f"Issues recorded: {len(report.issues)}")
    for issue in report.issues:
        if issue.status != "Valid":
            print(f"[{issue.status}] {issue.file_name} / {issue.field_or_rule}: {issue.message}")
            if issue.correction:
                print(f"  Correction: {issue.correction}")
    print(f"Report written to: {output_path.relative_to(ROOT)}")
    return 0 if report.overall_status != "Blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())

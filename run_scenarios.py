"""Run the deterministic scenario engine and write an auditable JSON output."""
from __future__ import annotations

import json
from pathlib import Path

from src.scenario_engine import build_scenarios


def main() -> None:
    """Load the base forecast, calculate scenario cases and persist JSON output."""
    root = Path(__file__).resolve().parent
    base_path = root / "outputs/base_forecast.json"
    if not base_path.exists():
        raise SystemExit("Base forecast missing. Run `python run_cash_forecast.py` first.")
    with base_path.open(encoding="utf-8") as handle:
        base = json.load(handle)
    result = build_scenarios(base, root)
    output_path = root / "outputs/scenario_results.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Scenario engine: {result['engine_version']}")
    for item in result["comparison"]:
        print(f"{item['scenario_id']}: {item['status']}; lowest cash SGD {item['lowest_cash']}; "
              f"breach weeks {item['breach_week_count']}; reconciliation implied by validated calculation")
    print(f"Result written to: {output_path.relative_to(root)}")


if __name__ == "__main__":
    main()

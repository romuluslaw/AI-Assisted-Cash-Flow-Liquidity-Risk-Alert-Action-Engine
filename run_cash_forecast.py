"""Run the deterministic cash engine and persist its JSON result contract."""
from __future__ import annotations

import json
from pathlib import Path

from src.cash_engine import CashEngineError, calculate_cash_forecast

ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Calculate the forecast, write the auditable result, and print key metrics."""
    output_path = ROOT / "outputs" / "base_forecast.json"
    try:
        result = calculate_cash_forecast(ROOT)
    except CashEngineError as exc:
        print(f"Cash forecast blocked: {exc}")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"Forecast status: {result.status}")
    print(f"Reconciliation: {result.reconciliation_status}")
    print(f"Lowest projected cash: {result.currency} {result.lowest_cash:,.2f} (Week {result.lowest_cash_week})")
    print(f"Minimum cash reserve: {result.currency} {result.minimum_cash_reserve:,.2f}")
    print(f"Maximum reserve shortfall: {result.currency} {result.maximum_reserve_shortfall:,.2f}")
    print(f"Opening cash below reserve: {result.opening_cash_below_reserve}")
    print(f"First closing-balance breach week: {result.first_breach_week}")
    print(f"Weeks below reserve: {result.breach_week_count}")
    print(f"Recovery week: {result.recovery_week}")
    print(f"Outside-horizon movements: {len(result.outside_horizon_movements)}")
    print(f"Result written to: {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

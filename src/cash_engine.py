"""Deterministic 13-week cash forecast calculations for Project 05.

Python is the sole authority for cash arithmetic and scenario-ready outputs.
No AI model is called from this module.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from src.input_validation import validate_project_inputs

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class CashEngineError(RuntimeError):
    """Raised when the cash engine cannot safely calculate a forecast."""


@dataclass(frozen=True)
class CashMovement:
    """One traceable cash movement used by the weekly cash forecast.

    `amount` is always a positive currency amount. `direction` is either
    `receipt` or `payment`; the weekly cash engine applies the sign.
    `source_type` distinguishes known transactions from estimates.
    """

    movement_id: str
    week_index: int | None
    movement_date: str | None
    amount: Decimal
    direction: str
    source_type: str
    category: str
    description: str
    outside_horizon: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe record while preserving currency precision."""
        result = asdict(self)
        result["amount"] = format(self.amount.quantize(CENT), ".2f")
        return result


@dataclass(frozen=True)
class WeeklyCashResult:
    """Reconciled weekly cash result and its known/estimated components."""

    week_index: int
    week_start_date: str
    opening_cash: Decimal
    known_receipts: Decimal
    estimated_receipts: Decimal
    known_payments: Decimal
    estimated_payments: Decimal
    total_receipts: Decimal
    total_payments: Decimal
    closing_cash: Decimal
    reserve_status: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe weekly result with two-decimal money values."""
        result = asdict(self)
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = format(value.quantize(CENT), ".2f")
        return result


@dataclass(frozen=True)
class CashForecastResult:
    """Complete deterministic forecast, diagnostics and traceable movements."""

    status: str
    currency: str
    forecast_start_date: str
    horizon_weeks: int
    opening_cash: Decimal
    minimum_cash_reserve: Decimal
    opening_cash_below_reserve: bool
    weeks: tuple[WeeklyCashResult, ...]
    movements: tuple[CashMovement, ...]
    outside_horizon_movements: tuple[CashMovement, ...]
    lowest_cash: Decimal
    lowest_cash_week: int
    maximum_reserve_shortfall: Decimal
    first_breach_week: int | None
    breach_week_count: int
    recovery_week: int | None
    reserve_restored_for_horizon: bool
    total_receipts: Decimal
    total_payments: Decimal
    reconciliation_status: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert the full result to a JSON-safe contract for logs and UI."""
        def money(value: Decimal) -> str:
            """Format one currency value for the JSON result contract."""
            return format(value.quantize(CENT), ".2f")

        return {
            "status": self.status,
            "currency": self.currency,
            "forecast_start_date": self.forecast_start_date,
            "horizon_weeks": self.horizon_weeks,
            "opening_cash": money(self.opening_cash),
            "minimum_cash_reserve": money(self.minimum_cash_reserve),
            "opening_cash_below_reserve": self.opening_cash_below_reserve,
            "weeks": [week.to_dict() for week in self.weeks],
            "movements": [movement.to_dict() for movement in self.movements],
            "outside_horizon_movements": [movement.to_dict() for movement in self.outside_horizon_movements],
            "lowest_cash": money(self.lowest_cash),
            "lowest_cash_week": self.lowest_cash_week,
            "maximum_reserve_shortfall": money(self.maximum_reserve_shortfall),
            "first_breach_week": self.first_breach_week,
            "breach_week_count": self.breach_week_count,
            "recovery_week": self.recovery_week,
            "reserve_restored_for_horizon": self.reserve_restored_for_horizon,
            "total_receipts": money(self.total_receipts),
            "total_payments": money(self.total_payments),
            "reconciliation_status": self.reconciliation_status,
            "warnings": list(self.warnings),
        }


def _read_json(path: Path) -> dict[str, Any]:
    """Load a previously validated JSON object from a project input path."""
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise CashEngineError(f"Expected a JSON object in {path.name}.")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Load validated UTF-8 CSV rows while preserving original field names."""
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _money(value: Any) -> Decimal:
    """Convert an input number to exact decimal currency and round to cents."""
    try:
        amount = Decimal(str(value))
    except Exception as exc:  # defensive boundary; validation should catch this first
        raise CashEngineError(f"Invalid currency amount {value!r}.") from exc
    if not amount.is_finite() or amount < 0:
        raise CashEngineError(f"Currency amount must be finite and non-negative: {value!r}.")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _week_index(transaction_date: date, forecast_start: date, horizon: int) -> int | None:
    """Map a date to its one-based seven-day forecast week, or outside horizon."""
    offset_days = (transaction_date - forecast_start).days
    if offset_days < 0:
        return None
    index = offset_days // 7 + 1
    return index if index <= horizon else None


def _historical_week_count(rows: list[dict[str, str]]) -> int:
    """Count distinct historical calendar weeks represented in payment history."""
    weeks = {date.fromisoformat(row["payment_date"]).isocalendar()[:2] for row in rows}
    return len(weeks)


def _add_movement(
    movements: list[CashMovement], *, movement_id: str, week_index: int | None,
    movement_date: date | None, amount: Decimal, direction: str, source_type: str,
    category: str, description: str, outside_horizon: bool = False,
) -> None:
    """Append a movement with consistent positive-amount and direction semantics."""
    movements.append(CashMovement(
        movement_id=movement_id,
        week_index=week_index,
        movement_date=movement_date.isoformat() if movement_date else None,
        amount=amount.quantize(CENT),
        direction=direction,
        source_type=source_type,
        category=category,
        description=description,
        outside_horizon=outside_horizon,
    ))


def _build_known_movements(
    root: Path, start: date, horizon: int, movements: list[CashMovement]
) -> list[CashMovement]:
    """Load invoice-backed receipts and scheduled payments into movement records.

    Amounts remain positive; the `direction` field determines their cash effect.
    Dates outside the horizon are retained for disclosure and excluded from weeks.
    """
    outside: list[CashMovement] = []
    for row in _read_csv(root / "data/input/customer_receipts.csv"):
        tx_date = date.fromisoformat(row["expected_date"])
        week = _week_index(tx_date, start, horizon)
        is_outside = week is None
        category = "Major customer receipt" if row["is_major_stress_target"].strip().lower() == "true" else "Customer receipt"
        _add_movement(
            movements, movement_id=row["transaction_id"], week_index=week,
            movement_date=tx_date, amount=_money(row["amount"]), direction="receipt",
            source_type="known", category=category,
            description=f"Customer {row['customer_id']} invoice-backed receipt",
            outside_horizon=is_outside,
        )
        if is_outside:
            outside.append(movements[-1])

    for row in _read_csv(root / "data/input/known_payments.csv"):
        tx_date = date.fromisoformat(row["expected_date"])
        week = _week_index(tx_date, start, horizon)
        is_outside = week is None
        _add_movement(
            movements, movement_id=row["transaction_id"], week_index=week,
            movement_date=tx_date, amount=_money(row["amount"]), direction="payment",
            source_type="known", category=row["category"],
            description=f"Scheduled payment; deferrable={row['deferrable']}",
            outside_horizon=is_outside,
        )
        if is_outside:
            outside.append(movements[-1])
    return outside


def _build_non_major_collection_estimates(
    root: Path, start: date, horizon: int, movements: list[CashMovement]
) -> tuple[list[CashMovement], list[str]]:
    """Apply documented collection shares to future-sales cohorts.

    Each bounded timing bucket's share is spread evenly across its lag weeks.
    The explicitly named `beyond_horizon` share is kept outside the 13-week
    totals, and any bounded-bucket allocation landing after Week 13 is also
    tracked outside the horizon. Invoice-backed receipts are a separate stream.
    """
    assumptions = _read_json(root / "config/collection_assumptions.json")
    sales_rows = _read_csv(root / "data/input/forecast_non_major_sales.csv")
    outside: list[CashMovement] = []
    warnings: list[str] = []
    buckets = assumptions["timing_buckets"]

    for row in sales_rows:
        cohort_week = int(row["week_index"])
        sales = _money(row["forecast_sales"])
        for bucket in buckets:
            share = Decimal(str(bucket["collection_share"]))
            bucket_name = bucket["bucket"]
            if bucket_name == "beyond_horizon":
                amount = (sales * share).quantize(CENT, rounding=ROUND_HALF_UP)
                if amount:
                    movement = CashMovement(
                        movement_id=f"EST_COLLECTION_W{cohort_week:02d}_{bucket_name}",
                        week_index=None, movement_date=None, amount=amount,
                        direction="receipt", source_type="estimated",
                        category="Non-major customer collections",
                        description=f"{bucket_name} share of Week {cohort_week} sales cohort; assumed outside horizon",
                        outside_horizon=True,
                    )
                    movements.append(movement)
                    outside.append(movement)
                continue

            min_lag = int(bucket["min_lag_weeks"])
            max_lag = int(bucket["max_lag_weeks"])
            lag_count = max_lag - min_lag + 1
            per_lag = (sales * share / Decimal(lag_count)).quantize(CENT, rounding=ROUND_HALF_UP)
            # Allocate rounding residual to the final lag so each bucket reconciles to its share.
            allocated = ZERO
            for lag in range(min_lag, max_lag + 1):
                lag_amount = per_lag
                if lag == max_lag:
                    target = (sales * share).quantize(CENT, rounding=ROUND_HALF_UP)
                    lag_amount = target - allocated
                allocated += lag_amount
                receipt_week = cohort_week + lag
                if receipt_week <= horizon:
                    receipt_date = start + timedelta(weeks=receipt_week - 1)
                    _add_movement(
                        movements,
                        movement_id=f"EST_COLLECTION_W{cohort_week:02d}_{bucket_name}_L{lag}",
                        week_index=receipt_week, movement_date=receipt_date,
                        amount=lag_amount, direction="receipt", source_type="estimated",
                        category="Non-major customer collections",
                        description=f"{bucket_name} share from Week {cohort_week} sales cohort; lag {lag} week(s)",
                    )
                else:
                    movement = CashMovement(
                        movement_id=f"EST_COLLECTION_W{cohort_week:02d}_{bucket_name}_L{lag}",
                        week_index=None, movement_date=None, amount=lag_amount,
                        direction="receipt", source_type="estimated",
                        category="Non-major customer collections",
                        description=f"{bucket_name} share from Week {cohort_week} sales cohort; lag {lag}; beyond Week {horizon}",
                        outside_horizon=True,
                    )
                    movements.append(movement)
                    outside.append(movement)

    return outside, warnings


def _build_payroll_estimates(
    root: Path, start: date, horizon: int, movements: list[CashMovement]
) -> list[str]:
    """Add forecast payroll as a cash outflow, net of any scheduled payroll.

    The forecast payroll file represents the weekly payroll requirement. If a
    scheduled payment already records part of payroll for the same week, only
    the positive remainder is estimated to avoid counting the same obligation
    twice. Scheduled payments remain in the known-payment stream.
    """
    warnings: list[str] = []
    scheduled_by_week: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for movement in movements:
        if (movement.direction == "payment" and movement.source_type == "known"
                and movement.category.strip().casefold() == "payroll"
                and movement.week_index is not None):
            scheduled_by_week[movement.week_index] += movement.amount

    for row in _read_csv(root / "data/input/forecast_payroll.csv"):
        week = int(row["week_index"])
        forecast_amount = _money(row["forecast_payroll"])
        scheduled = scheduled_by_week[week]
        remainder = max(ZERO, forecast_amount - scheduled).quantize(CENT, rounding=ROUND_HALF_UP)
        if scheduled > forecast_amount:
            warnings.append(
                f"Week {week}: scheduled payroll {scheduled:.2f} exceeds forecast payroll "
                f"{forecast_amount:.2f}; no additional payroll estimate was added."
            )
        if remainder == ZERO:
            continue
        week_date = date.fromisoformat(row["week_start_date"])
        _add_movement(
            movements, movement_id=f"EST_PAYROLL_W{week:02d}", week_index=week,
            movement_date=week_date, amount=remainder, direction="payment",
            source_type="estimated", category="Payroll",
            description=(f"Forecast weekly payroll {forecast_amount:.2f} less scheduled payroll "
                        f"{scheduled:.2f}, floored at zero"),
        )
    return warnings


def _build_claims_estimates(
    root: Path, start: date, horizon: int, movements: list[CashMovement]
) -> None:
    """Estimate weekly staff claims from historical claims as a share of payroll.

    This is an estimated cash outflow, not a confirmed liability. The calculation
    uses the documented claims-paid/payroll ratio and forecast weekly payroll.
    """
    claims_row = _read_csv(root / "data/input/historical_claims_payroll.csv")[0]
    historical_claims = _money(claims_row["claims_paid_amount"])
    historical_payroll = _money(claims_row["payroll_amount"])
    if historical_payroll <= ZERO:
        raise CashEngineError("Historical payroll must be greater than zero to estimate claims.")
    claims_rate = historical_claims / historical_payroll

    for row in _read_csv(root / "data/input/forecast_payroll.csv"):
        week = int(row["week_index"])
        payroll = _money(row["forecast_payroll"])
        amount = (payroll * claims_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        week_date = date.fromisoformat(row["week_start_date"])
        _add_movement(
            movements, movement_id=f"EST_CLAIMS_W{week:02d}", week_index=week,
            movement_date=week_date, amount=amount, direction="payment",
            source_type="estimated", category="Staff claims",
            description=f"Forecast payroll × historical claims rate ({claims_rate:.4%})",
        )


def _build_adhoc_baseline_estimates(
    root: Path, start: date, horizon: int, movements: list[CashMovement], config: dict[str, Any]
) -> list[str]:
    """Spread category-level historical ad hoc payments across the horizon.

    Category weekly baseline is historical category total divided by distinct
    historical weeks. For baseline-designated categories, known scheduled
    payments in the same category and forecast week are subtracted, floored at
    zero, before the estimated remainder is recorded.
    """
    rows = _read_csv(root / "data/input/historical_adhoc_payments.csv")
    weeks_observed = _historical_week_count(rows)
    minimum = int(config["ad_hoc_baseline_min_weeks"])
    preferred = int(config["ad_hoc_baseline_preferred_weeks"])
    warnings: list[str] = []
    if weeks_observed < minimum:
        raise CashEngineError(
            f"Ad hoc payment history covers {weeks_observed} distinct weeks; at least {minimum} are required."
        )
    if weeks_observed < preferred:
        warnings.append(
            f"Ad hoc payment history covers {weeks_observed} weeks; {preferred} weeks are preferred."
        )

    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        totals[row["category"]] += _money(row["amount"])
    baseline_by_category = {
        category: (total / Decimal(weeks_observed)).quantize(CENT, rounding=ROUND_HALF_UP)
        for category, total in totals.items()
    }

    known_by_category_week: dict[tuple[str, int], Decimal] = defaultdict(lambda: ZERO)
    for movement in movements:
        if movement.direction == "payment" and movement.source_type == "known" and movement.week_index is not None:
            known_by_category_week[(movement.category, movement.week_index)] += movement.amount

    for category, weekly_baseline in baseline_by_category.items():
        for week in range(1, horizon + 1):
            scheduled = known_by_category_week[(category, week)]
            remainder = max(ZERO, weekly_baseline - scheduled).quantize(CENT, rounding=ROUND_HALF_UP)
            if remainder == ZERO:
                continue
            week_date = start + timedelta(weeks=week - 1)
            _add_movement(
                movements, movement_id=f"EST_ADHOC_{category.upper().replace(' ', '_')}_W{week:02d}",
                week_index=week, movement_date=week_date, amount=remainder,
                direction="payment", source_type="estimated", category=category,
                description=(f"Historical category baseline {weekly_baseline:.2f} less scheduled "
                            f"same-category payments {scheduled:.2f}, floored at zero"),
            )
    return warnings


def _weekly_results(
    movements: list[CashMovement], start: date, horizon: int, opening_cash: Decimal,
    reserve: Decimal,
) -> tuple[WeeklyCashResult, ...]:
    """Aggregate eligible movements into weeks and roll forward closing cash."""
    totals: dict[tuple[int, str, str], Decimal] = defaultdict(lambda: ZERO)
    for movement in movements:
        if movement.week_index is None or movement.outside_horizon:
            continue
        totals[(movement.week_index, movement.direction, movement.source_type)] += movement.amount

    results: list[WeeklyCashResult] = []
    opening = opening_cash
    for week in range(1, horizon + 1):
        known_receipts = totals[(week, "receipt", "known")]
        estimated_receipts = totals[(week, "receipt", "estimated")]
        known_payments = totals[(week, "payment", "known")]
        estimated_payments = totals[(week, "payment", "estimated")]
        total_receipts = known_receipts + estimated_receipts
        total_payments = known_payments + estimated_payments
        closing = (opening + total_receipts - total_payments).quantize(CENT, rounding=ROUND_HALF_UP)
        status = "Compliant" if closing >= reserve else "Breach"
        results.append(WeeklyCashResult(
            week_index=week, week_start_date=(start + timedelta(weeks=week - 1)).isoformat(),
            opening_cash=opening, known_receipts=known_receipts, estimated_receipts=estimated_receipts,
            known_payments=known_payments, estimated_payments=estimated_payments,
            total_receipts=total_receipts, total_payments=total_payments,
            closing_cash=closing, reserve_status=status,
        ))
        opening = closing
    return tuple(results)


def calculate_cash_forecast(project_root: str | Path) -> CashForecastResult:
    """Validate inputs and calculate the deterministic 13-week cash forecast.

    Args:
        project_root: Root folder containing `config/`, `data/input/`, and `src/`.

    Returns:
        A complete result object with weekly balances, traceable movements,
        reserve exposure, reconciliation status and outside-horizon disclosures.

    Raises:
        CashEngineError: If critical input validation fails or a required estimate
            cannot be calculated safely. No AI model or external service is called.
    """
    root = Path(project_root).resolve()
    validation = validate_project_inputs(root)
    if validation.overall_status == "Blocked":
        details = "; ".join(issue.message for issue in validation.issues if issue.status == "Blocked")
        raise CashEngineError(f"Input validation blocked cash forecast: {details}")

    config = _read_json(root / "config/forecast_config.json")
    start = date.fromisoformat(config["forecast_start_date"])
    horizon = int(config["horizon_weeks"])
    opening_cash = _money(config["opening_cash"])
    reserve = _money(config["minimum_cash_reserve"])
    currency = str(config["currency"])
    movements: list[CashMovement] = []
    outside: list[CashMovement] = []
    warnings = [issue.message for issue in validation.issues if issue.status == "Warning"]

    outside.extend(_build_known_movements(root, start, horizon, movements))
    collection_outside, collection_warnings = _build_non_major_collection_estimates(root, start, horizon, movements)
    outside.extend(collection_outside)
    warnings.extend(collection_warnings)
    warnings.extend(_build_payroll_estimates(root, start, horizon, movements))
    _build_claims_estimates(root, start, horizon, movements)
    warnings.extend(_build_adhoc_baseline_estimates(root, start, horizon, movements, config))

    weeks = _weekly_results(movements, start, horizon, opening_cash, reserve)
    closing_values = [week.closing_cash for week in weeks]
    lowest_cash = min(closing_values)
    lowest_week = next(week.week_index for week in weeks if week.closing_cash == lowest_cash)
    breach_weeks = [week.week_index for week in weeks if week.closing_cash < reserve]
    first_breach = breach_weeks[0] if breach_weeks else None
    recovery_week = None
    if first_breach is not None:
        recovery_week = next(
            (week.week_index for week in weeks if week.week_index > first_breach and week.closing_cash >= reserve),
            None,
        )
    breach_count = len(breach_weeks)
    shortfall = max(ZERO, reserve - lowest_cash).quantize(CENT, rounding=ROUND_HALF_UP)
    total_receipts = sum((week.total_receipts for week in weeks), ZERO)
    total_payments = sum((week.total_payments for week in weeks), ZERO)
    expected_final = (opening_cash + total_receipts - total_payments).quantize(CENT, rounding=ROUND_HALF_UP)
    reconciliation_status = "Reconciled" if weeks[-1].closing_cash == expected_final else "Failed"
    if reconciliation_status != "Reconciled":
        raise CashEngineError("Weekly cash roll-forward does not reconcile to the 13-week total.")

    opening_cash_below_reserve = opening_cash < reserve
    if opening_cash_below_reserve:
        warnings.append("Opening cash is already below the configured minimum cash reserve.")

    return CashForecastResult(
        status="Breach projected" if (breach_count or opening_cash_below_reserve) else "Reserve maintained",
        currency=currency, forecast_start_date=start.isoformat(), horizon_weeks=horizon,
        opening_cash=opening_cash, minimum_cash_reserve=reserve,
        opening_cash_below_reserve=opening_cash_below_reserve, weeks=weeks,
        movements=tuple(movements), outside_horizon_movements=tuple(outside),
        lowest_cash=lowest_cash, lowest_cash_week=lowest_week,
        maximum_reserve_shortfall=shortfall, first_breach_week=first_breach,
        breach_week_count=breach_count, recovery_week=recovery_week,
        reserve_restored_for_horizon=(breach_count == 0 and not opening_cash_below_reserve),
        total_receipts=total_receipts,
        total_payments=total_payments, reconciliation_status=reconciliation_status,
        warnings=tuple(warnings),
    )

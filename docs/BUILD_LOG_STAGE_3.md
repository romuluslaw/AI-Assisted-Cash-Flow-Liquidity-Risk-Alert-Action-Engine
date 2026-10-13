# Stage 3 Build Log — Scenario Engine

## Scope delivered
- Added deterministic transformations for base, customer-delay, supplier-deferral, combined stress, and a separate accelerated-receipt action case.
- Default stress/action timing: 7 days; allowed range: integer 0–14 days.
- Only the configured designated major receipt is delayed or accelerated.
- Only known payments marked `deferrable=true` are deferred; protected categories are excluded.
- Scenario cash weeks and reserve metrics are recalculated from the movement ledger.
- Scenario movement logs preserve amount and record original/scenario dates. Deferral is explicitly timing-only.
- Output includes weekly balances, comparison metrics, action logs, and outside-horizon movement counts and amounts.

## Verification
- Unit tests include independent weekly roll-forward and horizon reconciliation checks, movement eligibility checks, amount-preservation checks, invalid-control rejection, and no-mutation checks.
- Run the final commands listed in the delivery message; the recorded verification reflects the build environment and does not certify other machines or Python versions.

## Known limitations
- Synthetic data only. Scenario delays and deferrals are deterministic assumptions, not predictions or confirmations from customers/suppliers.
- The scenario engine shifts dated eligible movements by calendar days and reassigns them to forecast weeks. It does not assume any payment is waived.
- No AI calls, external integrations, or paid services are used.

"""Streamlit executive dashboard for the deterministic liquidity risk engine.

All monetary calculations are performed by the validated Python engines. This
module only presents persisted results and exposes a controlled refresh action.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from src.scenario_engine import build_scenarios
from src.ai_ready import build_evidence_package, deterministic_cfo_brief
from src.ollama_client import check_ollama, generate_cfo_analysis

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
BASE_PATH = OUTPUTS / "base_forecast.json"
SCENARIO_PATH = OUTPUTS / "scenario_results.json"
VALIDATION_PATH = OUTPUTS / "validation_report.json"
AI_SETTINGS_PATH = ROOT / "config" / "ai_settings.json"
EVIDENCE_PATH = OUTPUTS / "cfo_evidence_package.json"


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON output file and return its top-level object.

    A missing or malformed file is allowed to raise an explicit exception so
    the dashboard can show a blocked state rather than presenting stale data.
    """
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path.name}.")
    return payload


def safe_md(text: Any) -> str:
    """Escape '$' so Streamlit never treats text between two dollar signs as a LaTeX formula."""
    return str(text).replace("$", "\\$")


def money(value: Any) -> str:
    """Format a numeric-like value as a clearly labelled SGD amount."""
    return f"SGD {float(value):,.0f}"


def money_thousands(value: Any) -> str:
    """Format a monetary KPI compactly in thousands of SGD."""
    return f"SGD {float(value) / 1000:,.1f}k"


def load_dashboard_data() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load validation, base forecast and scenario outputs as one UI snapshot."""
    validation = read_json(VALIDATION_PATH)
    base = read_json(BASE_PATH)
    scenarios = read_json(SCENARIO_PATH)
    if validation.get("overall_status") != "Valid":
        raise ValueError("Input validation is not Valid; refresh and resolve inputs before review.")
    if base.get("reconciliation_status") != "Reconciled":
        raise ValueError("Base forecast is not reconciled; dashboard assessment is blocked.")
    if not scenarios.get("scenarios") or not scenarios.get("comparison"):
        raise ValueError("Scenario results are missing; dashboard assessment is blocked.")
    if any(item.get("reconciliation_status") != "Reconciled" for item in scenarios["scenarios"]):
        raise ValueError("At least one scenario is not reconciled; dashboard assessment is blocked.")
    return validation, base, scenarios


def refresh_outputs() -> None:
    """Re-run validation, base forecast and scenarios in dependency order.

    subprocess.run uses the active Python interpreter and project root, avoiding
    reliance on the launcher's current working directory.
    """
    for script in ("run_validation.py", "run_cash_forecast.py", "run_scenarios.py"):
        completed = subprocess.run(
            [sys.executable, script], cwd=ROOT, capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "No diagnostic output."
            raise RuntimeError(f"{script} failed (exit {completed.returncode}): {detail}")


def scenario_table(comparison: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a compact CFO-oriented comparison using only decision-relevant metrics."""
    labels = {
        "base": "Base",
        "customer_delay": "Customer delay",
        "supplier_deferral": "Supplier deferral",
        "combined_stress": "Combined stress",
        "accelerated_receipt_action": "Receipt accelerated",
    }
    rows = []
    for item in comparison:
        rows.append({
            "Scenario": labels.get(item.get("scenario_id"), item.get("scenario_id", "Unknown")),
            "Status": item.get("status", "Unknown"),
            "Lowest cash (SGD '000)": float(item["lowest_cash"]) / 1000,
            "First breach": f"Week {item['first_breach_week']}" if item.get("first_breach_week") else "None",
            "Shortfall (SGD '000)": float(item["maximum_reserve_shortfall"]) / 1000,
            "Breach weeks": int(item.get("breach_week_count", 0)),
            "Recovery": f"Week {item['recovery_week']}" if item.get("recovery_week") else "Not applicable",
        })
    return pd.DataFrame(rows)


def cash_trajectory_chart(selected: dict[str, Any], reserve: float) -> alt.Chart:
    """Create a chronological cash chart with SGD-thousands axis and full-value tooltips."""
    weekly = pd.DataFrame(selected["weeks"]).sort_values("week_index")
    weekly["week_label"] = weekly["week_index"].map(lambda value: f"Week {value}")
    weekly["closing_thousands"] = weekly["closing_cash"].astype(float) / 1000
    weekly["reserve_thousands"] = reserve / 1000
    weekly["closing_cash_display"] = weekly["closing_cash"].astype(float)
    weekly["reserve_display"] = reserve
    cash = alt.Chart(weekly).encode(
        x=alt.X("week_index:O", sort=list(range(1, len(weekly) + 1)),
                axis=alt.Axis(title="Forecast week", labelExpr="'Week ' + datum.value")),
    )
    closing_line = cash.mark_line(point=alt.OverlayMarkDef(size=55)).encode(
        y=alt.Y("closing_thousands:Q", title="Closing cash (SGD '000)",
                axis=alt.Axis(format=",.0f")),
        tooltip=[alt.Tooltip("week_label:N", title="Week"),
                 alt.Tooltip("closing_cash_display:Q", title="Closing cash (SGD)", format=",.0f"),
                 alt.Tooltip("reserve_display:Q", title="Minimum reserve (SGD)", format=",.0f")],
        color=alt.value("#70C1FF"),
    )
    reserve_line = cash.mark_line(strokeDash=[6, 4], strokeWidth=2).encode(
        y=alt.Y("reserve_thousands:Q"), color=alt.value("#F59E0B"),
        tooltip=[alt.Tooltip("week_label:N", title="Week"),
                 alt.Tooltip("reserve_display:Q", title="Minimum reserve (SGD)", format=",.0f")],
    )
    return alt.layer(reserve_line, closing_line).resolve_scale(y="shared").properties(height=360).interactive()


st.set_page_config(page_title="Liquidity Risk Alert & Action Engine", page_icon="📊", layout="wide")
st.title("AI-Assisted Liquidity Risk Alert & Action Engine")
st.caption("Stage 6.3 · Executive liquidity dashboard · Synthetic demonstration data")
st.info("Python remains the financial source of truth. The local Ollama model (called only when you click Generate CFO Analysis) drafts a narrative from the validated evidence package; a deterministic Python fallback is always available. No cloud or external AI calls are made.")

with st.sidebar:
    st.subheader("Controls")
    st.write("Refresh re-runs input validation, the base forecast and all approved scenarios.")
    refresh_clicked = st.button("Refresh calculations", type="primary", use_container_width=True)
    st.divider()
    st.subheader("Simulation controls")
    customer_delay_days = st.slider("Major customer receipt delay (days)", 0, 14, 7,
                                    help="Moves only the designated major customer receipt. This is a stress assumption, not a prediction.")
    supplier_deferral_days = st.slider("Eligible supplier payment deferral (days)", 0, 14, 7,
                                       help="Moves only explicitly deferrable eligible payments; protected categories cannot be deferred.")
    st.caption("Receipt acceleration remains a separate predefined 7-day action scenario; it is not combined with stress cases.")
    st.divider()
    st.subheader("Local Ollama settings")
    ai_settings = read_json(AI_SETTINGS_PATH)
    ai_model_name = st.text_input("Ollama model tag", value=ai_settings.get("model_name", "gemma4:latest"),
                                  help="Use the exact tag shown by `ollama list` on this laptop.")
    ai_timeout = st.number_input("Timeout (seconds)", min_value=30, max_value=3600,
                                 value=int(ai_settings.get("timeout_seconds", 300)), step=30)
    ai_num_ctx = st.selectbox("Context window (tokens)", options=[4096, 8192, 12288, 16384],
                              index=[4096, 8192, 12288, 16384].index(int(ai_settings.get("num_ctx", 8192))))
    ai_num_predict = st.number_input("Reserved output tokens", min_value=128, max_value=2048,
                                     value=int(ai_settings.get("num_predict", 1000)), step=64)
    st.caption("Ollama is called only when you click Generate CFO Analysis. Requests target localhost only; no cloud or paid API is used.")
    st.caption("Review the assumptions, data quality and outside-horizon movements before acting on the forecast.")

if refresh_clicked:
    try:
        with st.spinner("Recalculating validated outputs…"):
            refresh_outputs()
        st.success("Outputs refreshed successfully. The dashboard has loaded the latest results.")
    except Exception as exc:  # UI boundary: show explicit failure and block stale assessment.
        st.error(f"Refresh failed. No refreshed assessment is available. Details: {exc}")
        st.stop()

try:
    validation, base, scenario_payload = load_dashboard_data()
except Exception as exc:
    st.error(f"Dashboard assessment blocked: {exc}")
    st.stop()

reserve = float(base["minimum_cash_reserve"])
lowest = float(base["lowest_cash"])
# Rebuild scenarios in memory from the validated base ledger so slider changes
# are reflected immediately without overwriting the persisted audit outputs.
try:
    scenario_payload = build_scenarios(
        base, ROOT,
        customer_delay_days=customer_delay_days,
        supplier_deferral_days=supplier_deferral_days,
        accelerated_receipt_days=7,
    )
except Exception as exc:
    st.error(f"Scenario simulation blocked: {exc}")
    st.stop()
comparison = scenario_table(scenario_payload["comparison"])

metric_cols = st.columns(4)
metric_cols[0].metric("Opening cash", money_thousands(base["opening_cash"]))
metric_cols[1].metric("Minimum reserve", money_thousands(reserve))
metric_cols[2].metric("Lowest base-case cash", money_thousands(lowest), f"Week {base['lowest_cash_week']}")
metric_cols[3].metric("Base-case reserve status", ("Below reserve" if base.get("opening_cash_below_reserve") or base.get("breach_week_count", 0) else "Within reserve"), f"Reserve: {money_thousands(reserve)}")

st.subheader("Executive findings")
# Present one concise, decision-oriented finding per case so the narrative never
# remains fixed on customer delay when the reviewer is exploring another case.
scenario_by_id = {item["scenario_id"]: item for item in scenario_payload["scenarios"]}
executive_cases = [
    ("customer_delay", "Customer Delay"),
    ("supplier_deferral", "Supplier Deferral"),
    ("combined_stress", "Combined Stress"),
    ("accelerated_receipt_action", "Accelerated Receipt Action"),
]
for case_id, heading in executive_cases:
    result = scenario_by_id[case_id]
    low = float(result["lowest_cash"])
    shortfall = float(result["maximum_reserve_shortfall"])
    breach = result.get("first_breach_week")
    recovery = result.get("recovery_week")
    if shortfall > 0:
        message = (f"First reserve breach: Week {breach}. Lowest closing cash: {money_thousands(low)} "
                   f"(Week {result['lowest_cash_week']}); maximum shortfall: {money(shortfall)}; "
                   f"below reserve for {result['breach_week_count']} week(s).")
        if recovery:
            message += f" Recovery above reserve: Week {recovery}."
        st.warning(f"**{heading}:** {message}")
    else:
        message = (f"Reserve maintained. Lowest closing cash: {money_thousands(low)} "
                   f"(Week {result['lowest_cash_week']}); no reserve-breach weeks.")
        if case_id == "supplier_deferral":
            message += " Deferral changes payment timing, not total payments, and requires supplier agreement."
        elif case_id == "accelerated_receipt_action":
            message += " This is a separate hypothetical action; confirm the customer can pay earlier."
        st.success(f"**{heading}:** {message}")
st.caption("Scenario outputs are decision-support estimates, not confirmed customer commitments or supplier agreements. Validate assumptions with accountable owners.")

st.subheader("Scenario comparison")
st.dataframe(
    comparison.style.format({
        "Lowest cash (SGD '000)": "{:,.1f}",
        "Shortfall (SGD '000)": "{:,.1f}",
    }), use_container_width=True, hide_index=True
)
st.caption("Amounts in the comparison are shown in SGD thousands. Detailed movement values remain available in the audit trail.")

scenario_options = {item["scenario_id"]: item for item in scenario_payload["scenarios"]}
scenario_labels = {
    "base": "Base case",
    "customer_delay": "Customer receipt delayed",
    "supplier_deferral": "Eligible supplier payments deferred",
    "combined_stress": "Combined stress",
    "accelerated_receipt_action": "Accelerated receipt action",
}
selected_id = st.selectbox(
    "Inspect weekly cash trajectory",
    options=list(scenario_options),
    format_func=lambda key: scenario_labels.get(key, key),
)
selected = scenario_options[selected_id]

with st.expander("CFO analysis — local Ollama", expanded=False):
    st.write("Python remains the source of truth for every financial figure. This button sends the validated evidence package to your local Ollama service only; output is schema-checked and generation time is recorded. Human review is required.")
    if st.button("Check local Ollama", use_container_width=True):
        status = check_ollama(ai_model_name)
        st.session_state["ollama_status"] = status
    if "ollama_status" in st.session_state:
        status = st.session_state["ollama_status"]
        if not status.get("available"):
            st.error(f"Local Ollama is not reachable: {status.get('error', 'unknown error')}. Start Ollama and retry.")
        elif not status.get("model_found"):
            st.error(f"Ollama is reachable but model tag '{ai_model_name}' was not found. Run `ollama list` and select the exact tag.")
            st.caption("Installed tags: " + (", ".join(status.get("installed_models", [])) or "none reported"))
        else:
            st.success(f"Local Ollama is reachable and {ai_model_name} is installed.")
    analysis_signature = (selected_id, int(customer_delay_days), int(supplier_deferral_days))
    if st.button("Generate CFO Analysis", type="primary", use_container_width=True):
        try:
            evidence_package = build_evidence_package(
                validation, base, scenario_payload, selected_id,
                model_name=ai_model_name, num_ctx=int(ai_num_ctx), num_predict=int(ai_num_predict),
                timeout_seconds=int(ai_timeout),
            )
            OUTPUTS.mkdir(exist_ok=True)
            EVIDENCE_PATH.write_text(json.dumps(evidence_package, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            st.session_state["cfo_evidence_package"] = evidence_package
            st.session_state["cfo_fallback_brief"] = deterministic_cfo_brief(evidence_package)
            st.session_state["cfo_analysis_signature"] = analysis_signature
            st.session_state.pop("cfo_model_analysis", None)
            st.session_state.pop("cfo_model_error", None)
            with st.spinner(f"Generating local analysis with {ai_model_name}… this can take a few minutes on a laptop."):
                analysis = generate_cfo_analysis(evidence_package, ai_model_name, int(ai_timeout), int(ai_num_ctx), int(ai_num_predict))
            st.session_state["cfo_model_analysis"] = analysis
            (OUTPUTS / "cfo_ollama_analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            st.session_state["cfo_model_error"] = f"{type(exc).__name__}: {exc}"
            st.session_state.pop("cfo_model_analysis", None)

    has_analysis = "cfo_model_analysis" in st.session_state
    has_error = "cfo_model_error" in st.session_state
    if (has_analysis or has_error) and st.session_state.get("cfo_analysis_signature") != analysis_signature:
        st.warning("The scenario or simulation settings have changed since this analysis was generated. Click Generate CFO Analysis to refresh it.")

    if has_analysis:
        analysis = st.session_state["cfo_model_analysis"]
        scenario_name = scenario_labels.get(st.session_state.get("cfo_analysis_signature", (selected_id,))[0], "")
        st.subheader(f"CFO analysis — {scenario_name}" if scenario_name else "CFO analysis")
        st.caption(f"Drafted locally by {analysis['model_name']} from validated Python figures in {analysis['generation_seconds']:.0f}s · Human review required before any action.")
        st.markdown("**Finding**")
        st.markdown(safe_md(analysis["finding"]))
        st.markdown("**Evidence**")
        for item in analysis["evidence"]:
            st.markdown(f"- {safe_md(item)}")
        st.markdown("**Risk**")
        st.markdown(safe_md(analysis["risk"]))
        st.markdown("**Recommended management actions**")
        for item in analysis["recommended_management_action"]:
            st.markdown(f"- {safe_md(item)}")
        if analysis["limitations"]:
            st.markdown("**Limitations**")
            for item in analysis["limitations"]:
                st.markdown(f"- {safe_md(item)}")
        with st.expander("Technical details and audit files"):
            st.caption(f"End-to-end {analysis['generation_seconds']:.1f}s · Ollama duration {analysis['ollama_total_duration_seconds']:.1f}s · Model load {analysis['ollama_load_duration_seconds']:.1f}s · "
                       f"prompt tokens {analysis.get('prompt_eval_count', 'n/a')} · generated tokens {analysis.get('generation_eval_count', 'n/a')} · retry used: {analysis.get('retry_used', False)}")
            budget = st.session_state["cfo_evidence_package"]["prompt_budget"]
            token_cols = st.columns(3)
            token_cols[0].metric("Estimated input tokens", f"{budget['estimated_input_tokens']:,}")
            token_cols[1].metric("Context + output budget", f"{budget['context_tokens']:,} + {budget['reserved_output_tokens']:,}")
            token_cols[2].metric("Budget check", "Within budget" if budget["within_configured_context"] else "Over budget")
            st.download_button("Download local AI briefing (JSON)", data=json.dumps(analysis, indent=2, ensure_ascii=False), file_name="cfo_ollama_analysis.json", mime="application/json")
            st.download_button("Download evidence package (audit JSON)", data=json.dumps(st.session_state["cfo_evidence_package"], indent=2, ensure_ascii=False, default=str), file_name="cfo_evidence_package.json", mime="application/json")
    elif has_error:
        # The rule-based briefing appears ONLY when the AI narrative is unavailable, so a reader never sees two competing versions.
        st.error("Local model analysis failed or was rejected. No AI narrative is presented as successful. A clearly labelled rule-based briefing is shown below instead. Details: " + st.session_state["cfo_model_error"])
        if "cfo_fallback_brief" in st.session_state:
            fallback_brief = st.session_state["cfo_fallback_brief"]
            st.subheader("Rule-based briefing — Python rules, not AI-generated")
            st.markdown(f"**Finding:** {safe_md(fallback_brief['finding'])}")
            st.markdown("**Evidence**")
            for item in fallback_brief["evidence"]:
                st.markdown(f"- {safe_md(item)}")
            st.markdown(f"**Risk:** {safe_md(fallback_brief['risk'])}")
            st.markdown("**Recommended management actions**")
            for item in fallback_brief["recommended_management_action"]:
                st.markdown(f"- {safe_md(item)}")
            st.download_button("Download evidence package (audit JSON)", data=json.dumps(st.session_state.get("cfo_evidence_package", {}), indent=2, ensure_ascii=False, default=str), file_name="cfo_evidence_package.json", mime="application/json")
            st.download_button("Download rule-based briefing (audit JSON)", data=json.dumps(fallback_brief, indent=2, ensure_ascii=False), file_name="cfo_rule_based_briefing.json", mime="application/json")

st.altair_chart(cash_trajectory_chart(selected, reserve), use_container_width=True)
first_breach = selected.get("first_breach_week")
recovery_week = selected.get("recovery_week")
breach_text = f"First reserve breach: Week {first_breach}." if first_breach else "No reserve breach in the forecast horizon."
recovery_text = f" Recovery above reserve: Week {recovery_week}." if recovery_week else ""
st.caption(
    f"Selected scenario: {selected.get('description', selected_id)}. "
    f"Lowest closing cash: {money(selected['lowest_cash'])} in Week {selected['lowest_cash_week']}. "
    f"{breach_text} Maximum shortfall: {money(selected['maximum_reserve_shortfall'])}. "
    f"Reserve-breach weeks: {selected['breach_week_count']}.{recovery_text}"
)

with st.expander("Accelerated receipt action — invoice register", expanded=True):
    st.write("**Hypothetical rule:** positive, invoice-backed known receipts are candidates only when both their original expected date and the date moved earlier by seven days remain within the 13-week forecast horizon. No customer commitment is implied.")
    register = scenario_payload.get("invoice_register", [])
    if register:
        register_frame = pd.DataFrame(register)
        register_frame["outstanding_amount"] = register_frame["outstanding_amount"].map(money)
        register_frame = register_frame.rename(columns={
            "invoice_reference": "Invoice reference", "customer_id": "Customer ID",
            "outstanding_amount": "Outstanding amount (SGD)",
            "original_expected_receipt_date": "Original expected date",
            "hypothetical_accelerated_date": "Hypothetical earlier date",
            "days_brought_forward": "Days earlier", "eligible_candidate": "Eligible candidate",
            "selected_for_action": "Included in action case", "confirmation_status": "Status",
            "eligibility_rationale": "Eligibility rationale",
        })
        st.dataframe(register_frame, use_container_width=True, hide_index=True)
        selected_candidates = [item for item in register if item.get("selected_for_action")]
        total_brought_forward = sum(float(item["outstanding_amount"]) for item in selected_candidates)
        st.metric("Invoice value included in hypothetical action", money_thousands(total_brought_forward),
                  help="Gross invoice value moved earlier in time, not incremental revenue or additional total receipts.")
        st.caption(f"{len(selected_candidates)} of {len(register)} known invoice-backed receipts selected. The action shifts dates only; it does not increase total receipts. Confirm feasibility with the collections owner before relying on it.")
    else:
        st.info("No invoice-backed receipts are available for the acceleration register.")

with st.expander("Data quality and auditability", expanded=True):
    quality_cols = st.columns(3)
    quality_cols[0].metric("Input validation", validation.get("overall_status", "Unknown"))
    quality_cols[1].metric("Base reconciliation", base.get("reconciliation_status", "Unknown"))
    quality_cols[2].metric("Scenarios reconciled", f"{sum(item.get('reconciliation_status') == 'Reconciled' for item in scenario_payload['scenarios'])}/{len(scenario_payload['scenarios'])}")
    st.write(f"**Forecast horizon:** {base.get('horizon_weeks')} weeks")
    st.write(f"**Forecast start date:** {base.get('forecast_start_date')}")
    st.write(f"**Outside-horizon movements in base case:** {len(base.get('outside_horizon_movements', []))}")
    st.write("**Validation detail:** All required input contracts must pass before the dashboard loads the financial assessment.")
    st.json({"validation_issues": validation.get("issues", []), "scenario_parameters": scenario_payload.get("parameters", {}), "base_warnings": base.get("warnings", [])})

with st.expander("Movement and action audit trail"):
    action_log = selected.get("action_log", [])
    if action_log:
        st.dataframe(pd.DataFrame(action_log), use_container_width=True, hide_index=True)
    else:
        st.write("No scenario actions were applied to this case.")
    outside = selected.get("outside_horizon_movements", [])
    st.write(f"Outside-horizon movement records: {len(outside)}")
    if outside:
        st.dataframe(pd.DataFrame(outside), use_container_width=True, hide_index=True)

st.divider()
st.caption("Decision support only. Confirm customer commitments, supplier agreements and underlying source data with accountable owners. No financing is assumed unless explicitly included in validated inputs.")

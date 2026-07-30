import json
import os
import re
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

load_dotenv()


class ReportState(TypedDict):
    profile: dict  # input, from profile_dataset()
    filename: str
    schema_summary: str
    overview_narrative: str
    anomaly_narrative: str
    correlation_narrative: str
    entity_narrative: str
    eda_narrative: str
    recommendations: List[str]
    final_report: dict


def _get_llm():
    """Initializes and returns the ChatGroq model instance."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        # Returns ChatGroq instance, fallback handling will catch missing key errors if any
        return ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, groq_api_key="mock_key_if_missing")
    return ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, groq_api_key=api_key)


def _invoke_llm_safely(system_prompt: str, user_prompt: str, fallback_text: str) -> str:
    """Helper to invoke LLM with system & user prompts, falling back gracefully if API call fails."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        return fallback_text

    try:
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, groq_api_key=api_key)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = llm.invoke(messages)
        return str(response.content).strip()
    except Exception as e:
        print(f"[report_pipeline] LLM invocation notice ({e}). Using deterministic summary fallback.")
        return fallback_text


def schema_node(state: ReportState) -> ReportState:
    """1. schema_node: Classifies the likely business/industrial meaning of each column."""
    columns_info = state["profile"].get("columns", [])
    cols_text = "\n".join([
        f"- Column: {c.get('name')}, Type: {c.get('dtype')}, Missing %: {c.get('missing_pct')}%, Unique/Stats: {c.get('unique_count', c.get('mean', 'N/A'))}"
        for c in columns_info
    ])

    system_prompt = (
        "You are analyzing an industrial dataset. Only use the column names and stats provided. "
        "Do not invent columns or values."
    )
    user_prompt = (
        f"Analyze the following columns from the dataset '{state.get('filename')}':\n\n"
        f"{cols_text}\n\n"
        "Classify the likely business/industrial meaning of each column in one short phrase "
        "(e.g., 'sensor reading', 'machine identifier', 'operational status flag', 'timestamp'). "
        "Output as a concise summary string describing the dataset schema structure."
    )

    fallback = f"The dataset contains {len(columns_info)} columns including temporal indices, machine identifiers, operational sensor measurements, and status indicators."
    schema_summary = _invoke_llm_safely(system_prompt, user_prompt, fallback)
    state["schema_summary"] = schema_summary
    return state


def summary_node(state: ReportState) -> ReportState:
    """2. summary_node: Generates a 2-3 paragraph plain-English dataset overview for plant managers."""
    shape = state["profile"].get("shape", {})
    memory_mb = state["profile"].get("memory_usage_mb", 0.0)
    columns_info = state["profile"].get("columns", [])

    missing_summary = "\n".join([
        f"- {c.get('name')}: {c.get('missing_pct')}% missing ({c.get('missing_count')} rows)"
        for c in columns_info
    ])

    system_prompt = (
        "Only reference numbers explicitly given below. If a number is not provided, do not state or estimate it."
    )
    user_prompt = (
        f"Dataset filename: {state.get('filename')}\n"
        f"Rows: {shape.get('rows', 0)}, Columns: {shape.get('columns', 0)}\n"
        f"Memory usage: {memory_mb} MB\n\n"
        f"Per-Column Data Quality & Missingness:\n{missing_summary}\n\n"
        "Write a 2-3 paragraph plain-English overview of the dataset's shape and data quality, "
        "written for a non-technical plant manager audience."
    )

    fallback = (
        f"The dataset '{state.get('filename')}' comprises {shape.get('rows', 0)} records across {shape.get('columns', 0)} attributes, "
        f"occupying approximately {memory_mb} MB of memory.\n\n"
        f"Overall data completeness is high across the monitored telemetry fields, providing a solid empirical baseline "
        "for equipment diagnostics and operational intelligence."
    )
    overview_narrative = _invoke_llm_safely(system_prompt, user_prompt, fallback)
    state["overview_narrative"] = overview_narrative
    return state


def anomaly_node(state: ReportState) -> ReportState:
    """3. anomaly_node: Explains anomalous rows and 3-sigma industrial signal threshold breaches."""
    anomalies = state["profile"].get("anomalies")
    ind_signals = state["profile"].get("industrial_signals", {})

    anomalies_str = json.dumps(anomalies) if anomalies else "None detected"
    signals_str = json.dumps(ind_signals) if ind_signals else "None detected"

    system_prompt = "You are an industrial data analyst. Do not invent anomalies or data values."
    user_prompt = (
        f"Isolation Forest Anomalies: {anomalies_str}\n"
        f"Industrial 3-Sigma Breach Signals: {signals_str}\n\n"
        "Write a narrative explaining what's anomalous and why it might matter operationally (e.g. equipment risk, safety, downtime). "
        "If anomalies is null or industrial_signals is empty/has no breaches, explicitly say no significant anomalies were detected — do not fabricate any."
    )

    # Deterministic fallback logic
    has_anomalies = anomalies and anomalies.get("anomalous_row_count", 0) > 0
    has_signals = any(v.get("threshold_breach_count", 0) > 0 for v in ind_signals.values()) if ind_signals else False

    if not has_anomalies and not has_signals:
        fallback = "No significant operational anomalies or 3-sigma threshold breaches were detected in this dataset."
    else:
        signal_details = []
        if ind_signals:
            for k, v in ind_signals.items():
                if v.get("threshold_breach_count", 0) > 0:
                    signal_details.append(f"{k}: {v.get('threshold_breach_count')} breach(es)")
        anom_txt = f"{anomalies.get('anomalous_row_count')} multivariate anomaly rows identified by Isolation Forest." if has_anomalies else ""
        sig_txt = f"3-sigma threshold breaches observed in: {', '.join(signal_details)}." if signal_details else ""
        fallback = f"Operational Anomaly Alert: {anom_txt} {sig_txt} These deviations indicate potential transient spikes, sensor noise, or impending component stress requiring inspection."

    anomaly_narrative = _invoke_llm_safely(system_prompt, user_prompt, fallback)
    state["anomaly_narrative"] = anomaly_narrative
    return state


def correlation_node(state: ReportState) -> ReportState:
    """4. correlation_node: Explains top numeric correlations in plain domain language."""
    correlations = state["profile"].get("correlations", [])
    corr_str = json.dumps(correlations[:5]) if correlations else "None"

    system_prompt = "You are an industrial data analyst. Analyze the correlation pairs provided."
    user_prompt = (
        f"Top Numeric Correlation Pairs:\n{corr_str}\n\n"
        "Explain the strongest 3-5 correlations or statistical relationships in plain domain language "
        "(e.g., 'X and Y moving together may indicate a shared failure mode or shared root cause'). "
        "Highlight whether they are strongly correlated (|r| > 0.7) or weakly correlated, and explain what this implies operationally."
    )

    if not correlations:
        fallback = "No numeric correlation pairs could be calculated for this dataset due to lack of multiple numeric columns."
    else:
        top_pairs = [f"{c['col_a']} & {c['col_b']} (r = {c['correlation']})" for c in correlations[:3]]
        fallback = f"Statistical relationship breakdown for key variables: {', '.join(top_pairs)}. Tracking co-trending behaviors helps identify thermodynamic coupling, control loop dynamics, and joint failure modes."

    correlation_narrative = _invoke_llm_safely(system_prompt, user_prompt, fallback)
    state["correlation_narrative"] = correlation_narrative
    return state


def eda_node(state: ReportState) -> ReportState:
    """8. eda_node: Generates a narrative summarizing exploratory data analysis findings."""
    profile = state["profile"]
    # Build a summary of the profile for the prompt
    shape = profile.get("shape", {})
    rows = shape.get("rows", 0)
    cols = shape.get("columns", 0)
    columns = profile.get("columns", [])
    missing_info = []
    for col in columns:
        if col.get("missing_pct", 0) > 0:
            missing_info.append(f'{col.get("name")}: {col.get("missing_pct")}% missing ({col.get("missing_count")} rows)')
    missing_str = "; ".join(missing_info) if missing_info else "No missing data"
    anomalies = profile.get("anomalies")
    anomalies_str = "None"
    if anomalies and anomalies.get("anomalous_row_count", 0) > 0:
        anomalies_str = f'{anomalies.get("anomalous_row_count")} anomalous rows ({anomalies.get("anomalous_row_pct", 0)}%)'
    correlations = profile.get("correlations", [])
    top_corr = []
    if correlations:
        sorted_corr = sorted(correlations, key=lambda x: abs(x["correlation"]), reverse=True)
        for c in sorted_corr[:3]:
            top_corr.append(f'{c["col_a"]} & {c["col_b"]}: r={c["correlation"]:.3f}')
    corr_str = "; ".join(top_corr) if top_corr else "No significant correlations"
    industrial = profile.get("industrial_signals", {})
    ind_str = []
    for col, sig in industrial.items():
        if sig.get("threshold_breach_count", 0) > 0:
            ind_str.append(f'{col}: {sig["threshold_breach_count"]} breaches ({sig["threshold_breach_pct"]}%)')
    ind_str = "; ".join(ind_str) if ind_str else "No industrial signal breaches"
    machine_breakdown = profile.get("machine_breakdown", [])
    mc_str = []
    for m in machine_breakdown[:3]:
        mc_str.append(f'{m.get("machine_id")}: {m.get("downtime_minutes")} mins downtime, severity={m.get("severity")}')
    mc_str = "; ".join(mc_str) if mc_str else "No machine breakdown data"
    prompt = (
        f"You are an industrial data analyst. Provide a concise, plain-English summary of the exploratory data analysis findings for a plant manager. "
        f"Use the following data:\n"
        f"- Dataset size: {rows} rows, {cols} columns\n"
        f"- Missing data: {missing_str}\n"
        f"- Outliers (Isolation Forest): {anomalies_str}\n"
        f"- Top correlations: {corr_str}\n"
        f"- Industrial signal breaches: {ind_str}\n"
        f"- Machine breakdown (top 3): {mc_str}\n"
        f"Write a paragraph summarizing the key insights and potential areas of concern for operations."
    )
    system_prompt = (
        "You are an industrial data analyst. Only use the provided data. Do not invent facts or numbers."
    )
    fallback = (
        f"The dataset contains {rows} records and {cols} attributes. "
        f"Exploratory data analysis reveals data quality indicators, outlier detection via Isolation Forest, correlation highlights, "
        f"and machine-level performance metrics. Refer to the detailed sections for specifics."
    )
    eda_narrative = _invoke_llm_safely(system_prompt, prompt, fallback)
    state["eda_narrative"] = eda_narrative
    return state


def entity_rollup_node(state: ReportState) -> ReportState:
    """7. entity_rollup_node: Generates a narrative for escalated and watched entities."""
    entity_rollup = state["profile"].get("entity_rollup")
    if not entity_rollup:
        state["entity_narrative"] = None
        return state

    system_prompt = (
        "You are an industrial operations analyst. Only use the numbers provided in the entity_rollup data. "
        "Do not invent entity names, values, or any additional details. "
        "Explain in plain language why each escalated or watched entity needs attention, referencing the actual counts provided."
    )

    # Format the entity_rollup data for the prompt, focusing on escalate and watch entities
    entities = entity_rollup.get("entities", [])
    escalate_entities = [e for e in entities if e.get("severity") == "escalate"]
    watch_entities = [e for e in entities if e.get("severity") == "watch"]

    # Build a summary string for the prompt
    details_lines = []
    for entity in escalate_entities + watch_entities:
        entity_id = entity.get("entity_id", "unknown")
        severity = entity.get("severity", "unknown")
        row_count = entity.get("row_count", 0)
        anomaly_count = entity.get("anomaly_count", 0)
        breach_count = entity.get("threshold_breach_count", 0)
        downtime_total = entity.get("downtime_total")
        fault_count = entity.get("fault_count", 0)

        line = f"- Entity {entity_id} ({severity}): {row_count} records, {anomaly_count} anomalies, {breach_count} threshold breaches"
        if downtime_total is not None:
            line += f", {downtime_total:.1f} minutes downtime"
        if fault_count:
            line += f", {fault_count} fault indicators"
        details_lines.append(line)

    details_str = "\n".join(details_lines) if details_lines else "No escalated or watched entities found."

    user_prompt = (
        f"Entity Rollup Summary:\n"
        f"Entity Column: {entity_rollup.get('entity_column', 'unknown')}\n"
        f"Total Entities: {entity_rollup.get('summary', {}).get('total_entities', 0)}\n"
        f"Escalate Count: {entity_rollup.get('summary', {}).get('escalate_count', 0)}\n"
        f"Watch Count: {entity_rollup.get('summary', {}).get('watch_count', 0)}\n"
        f"Normal Count: {entity_rollup.get('summary', {}).get('normal_count', 0)}\n\n"
        f"Entity Details:\n{details_str}\n\n"
        "Write a concise narrative (2-3 sentences) explaining why the escalated and watched entities require attention, "
        "referencing the specific numbers provided (anomaly count, threshold breaches, downtime, fault count). "
        "If there are no escalated or watched entities, state that all equipment appears normal."
    )

    fallback = "Entity risk analysis unavailable due to insufficient data or processing error."

    entity_narrative = _invoke_llm_safely(system_prompt, user_prompt, fallback)
    state["entity_narrative"] = entity_narrative
    return state


def recommendation_node(state: ReportState) -> ReportState:
    """5. recommendation_node: Generates 3-5 actionable recommendations as a JSON array of strings."""
    plant_exec = state["profile"].get("plant_executive_summary", {})
    m_breakdown = state["profile"].get("machine_breakdown", [])
    problem_child = plant_exec.get("problem_child_machine", "N/A")
    total_loss_inr = plant_exec.get("total_est_loss_inr", 0.0)
    total_downtime_mins = plant_exec.get("total_downtime_minutes", 0.0)
    overall_status = plant_exec.get("overall_status", "NORMAL OPERATIONAL PARAMETERS")
    anomalies = state["profile"].get("anomalies") or {}
    ind_signals = state["profile"].get("industrial_signals", {})

    # Build machine breakdown summary text for prompt
    machine_lines = []
    for m in m_breakdown[:5]:
        machine_lines.append(
            f"  - {m.get('machine_id')}: {m.get('downtime_minutes')} mins downtime, "
            f"severity={m.get('severity')}, est loss ₹{m.get('est_financial_loss_inr')}"
        )
    machine_text = "\n".join(machine_lines) if machine_lines else "  No per-machine breakdown available."

    # Build industrial signal breach text for prompt
    breach_lines = []
    for col, sig in ind_signals.items():
        if sig.get("threshold_breach_count", 0) > 0:
            breach_lines.append(f"  - {col}: {sig['threshold_breach_count']} breach(es) ({sig['threshold_breach_pct']}%)")
    breach_text = "\n".join(breach_lines) if breach_lines else "  No 3-sigma threshold breaches detected."

    system_prompt = (
        "You are an industrial plant operations advisor giving concise, actionable maintenance recommendations. "
        "Only reference the exact machine IDs, numbers, and signals provided. Do not invent data."
    )
    user_prompt = (
        f"Plant Health Status: {overall_status}\n"
        f"Problem Child Machine: {problem_child}\n"
        f"Total Downtime: {total_downtime_mins} minutes\n"
        f"Est. Total Production Loss: ₹{total_loss_inr:,.0f}\n"
        f"Anomalous Rows: {anomalies.get('anomalous_row_count', 0)}\n\n"
        f"Per-Machine Breakdown:\n{machine_text}\n\n"
        f"Industrial Signal Threshold Breaches:\n{breach_text}\n\n"
        "Generate exactly 4-5 concise, actionable maintenance recommendations for a plant manager. "
        "Each recommendation must be a plain English sentence. Reference specific machine IDs or signal names where relevant. "
        "Return ONLY a JSON array of strings, with no markdown, no code blocks, no preamble."
    )

    fallback_recs = [
        f"Prioritize inspection and preventive maintenance on {problem_child} — it accounts for the highest downtime and production loss.",
        "Implement continuous automated threshold monitoring for high-variance process signals.",
        "Inspect equipment sensors exhibiting 3-sigma deviations to verify calibration and physical wiring.",
        "Perform scheduled maintenance reviews on correlated machine parameters to mitigate shared failure risks.",
        "Establish baseline data validation rules to maintain high completeness across all operational logs.",
    ]

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        state["recommendations"] = fallback_recs
        return state

    try:
        llm = _get_llm()
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        res = llm.invoke(messages)
        content = str(res.content).strip()

        # Try parsing JSON
        parsed = _parse_json_array(content)
        if parsed:
            state["recommendations"] = parsed
            return state

        # Retry once with stricter instructions
        retry_messages = [
            SystemMessage(content="Return ONLY a JSON array of strings, with no markdown formatting, no code block backticks, and no preamble."),
            HumanMessage(content=f"Convert the following recommendations into a valid JSON array of 3-5 strings:\n{content}"),
        ]
        res_retry = llm.invoke(retry_messages)
        parsed_retry = _parse_json_array(str(res_retry.content).strip())
        state["recommendations"] = parsed_retry if parsed_retry else fallback_recs

    except Exception as e:
        print(f"[report_pipeline] Recommendation LLM notice ({e}). Using fallback recommendations.")
        state["recommendations"] = fallback_recs

    return state


def _parse_json_array(text: str) -> Optional[List[str]]:
    """Helper to extract and parse a JSON list of strings from LLM text output."""
    try:
        # Check if direct JSON string
        data = json.loads(text)
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data
    except Exception:
        pass

    # Regex search for [...] block
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return [str(item) for item in data if item]
        except Exception:
            pass
    return None


def compiler_node(state: ReportState) -> ReportState:
    """6. compiler_node: Merges all narrative fields & exact computed data quality stats into final_report."""
    columns_info = state["profile"].get("columns", [])

    # Exact computed data quality numbers directly from profile
    data_quality = {
        c.get("name", f"col_{i}"): {
            "dtype": c.get("dtype"),
            "missing_count": c.get("missing_count"),
            "missing_pct": c.get("missing_pct"),
        }
        for i, c in enumerate(columns_info)
    }

    # Build entity_analysis if entity_rollup exists
    entity_analysis = None
    entity_rollup = state["profile"].get("entity_rollup")
    if entity_rollup:
        entity_analysis = {
            "entity_column": entity_rollup.get("entity_column"),
            "narrative": state.get("entity_narrative"),
            "entities": entity_rollup.get("entities")
        }

    final_report = {
        "overview": state.get("overview_narrative", ""),
        "schema_summary": state.get("schema_summary", ""),
        "data_quality": data_quality,
        "key_trends": state.get("correlation_narrative", ""),
        "anomalies": state.get("anomaly_narrative", ""),
        "recommendations": state.get("recommendations", []),
        "raw_profile_reference": state.get("profile", {}),
        "entity_analysis": entity_analysis,
        "eda": state.get("eda_narrative", ""),
    }

    state["final_report"] = final_report
    return state


# Build & Compile LangGraph StateGraph
builder = StateGraph(ReportState)
builder.add_node("schema_node", schema_node)
builder.add_node("summary_node", summary_node)
builder.add_node("anomaly_node", anomaly_node)
builder.add_node("correlation_node", correlation_node)
builder.add_node("eda_node", eda_node)
builder.add_node("entity_rollup_node", entity_rollup_node)
builder.add_node("recommendation_node", recommendation_node)
builder.add_node("compiler_node", compiler_node)

builder.set_entry_point("schema_node")
builder.add_edge("schema_node", "summary_node")
builder.add_edge("summary_node", "anomaly_node")
builder.add_edge("anomaly_node", "correlation_node")
builder.add_edge("correlation_node", "eda_node")
builder.add_edge("eda_node", "entity_rollup_node")
builder.add_edge("entity_rollup_node", "recommendation_node")
builder.add_edge("recommendation_node", "compiler_node")
builder.add_edge("compiler_node", END)

report_graph = builder.compile()


def generate_report(profile: dict, filename: str) -> dict:
    """Builds initial state, executes compiled LangGraph pipeline, and returns final_report."""
    initial_state: ReportState = {
        "profile": profile,
        "filename": filename,
        "schema_summary": "",
        "overview_narrative": "",
        "anomaly_narrative": "",
        "correlation_narrative": "",
        "entity_narrative": "",
        "eda_narrative": "",
        "recommendations": [],
        "final_report": {},
    }

    final_state = report_graph.invoke(initial_state)
    return final_state.get("final_report", {})
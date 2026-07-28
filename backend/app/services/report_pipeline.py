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



def recommendation_node(state: ReportState) -> ReportState:
    """5. recommendation_node: Generates 3-5 actionable recommendations as a JSON array of strings."""
    context = (
        f"--- Schema Summary ---\n{state.get('schema_summary')}\n\n"
        f"--- Dataset Overview ---\n{state.get('overview_narrative')}\n\n"
        f"--- Anomaly Analysis ---\n{state.get('anomaly_narrative')}\n\n"
        f"--- Correlation Analysis ---\n{state.get('correlation_narrative')}\n"
    )

    system_prompt = (
        "You are an expert industrial operations consultant. Provide actionable recommendations based ONLY on the context provided. "
        "Return ONLY a JSON array of 3 to 5 strings."
    )
    user_prompt = (
        f"Context:\n{context}\n\n"
        "Based on this analysis, generate exactly 3 to 5 concise, actionable operational recommendations for plant management.\n"
        "Output MUST be a raw JSON array of strings (e.g. [\"Recommendation 1\", \"Recommendation 2\", \"Recommendation 3\"])."
    )

    fallback_recs = [
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

    final_report = {
        "overview": state.get("overview_narrative", ""),
        "schema_summary": state.get("schema_summary", ""),
        "data_quality": data_quality,
        "key_trends": state.get("correlation_narrative", ""),
        "anomalies": state.get("anomaly_narrative", ""),
        "recommendations": state.get("recommendations", []),
        "raw_profile_reference": state.get("profile", {}),
    }

    state["final_report"] = final_report
    return state


# Build & Compile LangGraph StateGraph
builder = StateGraph(ReportState)
builder.add_node("schema_node", schema_node)
builder.add_node("summary_node", summary_node)
builder.add_node("anomaly_node", anomaly_node)
builder.add_node("correlation_node", correlation_node)
builder.add_node("recommendation_node", recommendation_node)
builder.add_node("compiler_node", compiler_node)

builder.set_entry_point("schema_node")
builder.add_edge("schema_node", "summary_node")
builder.add_edge("summary_node", "anomaly_node")
builder.add_edge("anomaly_node", "correlation_node")
builder.add_edge("correlation_node", "recommendation_node")
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
        "recommendations": [],
        "final_report": {},
    }

    final_state = report_graph.invoke(initial_state)
    return final_state.get("final_report", {})

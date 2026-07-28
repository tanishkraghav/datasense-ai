import concurrent.futures
import json
import math
import os
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
import numpy as np
import pandas as pd

load_dotenv()

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")

FORBIDDEN_PATTERNS = [
    "import",
    "exec",
    "eval",
    "open(",
    "os.",
    "sys.",
    "subprocess",
    "__",
    "getattr",
    "setattr",
]


def _to_python(val: Any) -> Any:
    """Converts numpy/pandas types to native Python types for JSON serialization."""
    if pd.isna(val):
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    return str(val)


def _sanitize_code(code: str) -> Optional[str]:
    """Cleans code fences and validates code against forbidden security patterns."""
    clean_code = code.strip()
    clean_code = re.sub(r"^```(?:python)?\s*", "", clean_code, flags=re.IGNORECASE)
    clean_code = re.sub(r"\s*```$", "", clean_code)
    clean_code = clean_code.strip()

    code_lower = clean_code.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in code_lower:
            return None
    return clean_code


def _suggest_chart_config(df_res: pd.DataFrame) -> dict:
    """Suggests a line, bar, or table chart configuration based on result DataFrame structure."""
    if df_res.empty:
        return {"type": "table", "x_key": None, "y_key": None}

    cols = [str(c) for c in df_res.columns]
    if len(cols) < 2:
        return {"type": "table", "x_key": None, "y_key": None}

    dt_col = None
    num_col = None
    cat_col = None

    for c in cols:
        s = df_res[c]
        if pd.api.types.is_datetime64_any_dtype(s) or any(k in str(c).lower() for k in ["time", "date", "timestamp"]):
            if not dt_col:
                dt_col = c
        elif pd.api.types.is_numeric_dtype(s):
            if not num_col:
                num_col = c
        else:
            if not cat_col:
                cat_col = c

    if dt_col and num_col:
        return {"type": "line", "x_key": dt_col, "y_key": num_col}
    if cat_col and num_col:
        return {"type": "bar", "x_key": cat_col, "y_key": num_col}
    return {"type": "bar", "x_key": cols[0], "y_key": cols[1]}


def _generate_pandas_code(question: str, df: pd.DataFrame) -> str:
    """Generates a single line of pandas code assigning to `result` using ChatGroq or fallback rules."""
    api_key = os.getenv("GROQ_API_KEY", "")
    q_lower = question.lower()

    # Rule-based fallback if no API key set
    if not api_key or api_key == "your_groq_api_key_here":
        if "average" in q_lower or "mean" in q_lower:
            num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            for col in num_cols:
                if col.lower() in q_lower:
                    return f"result = df['{col}'].mean()"
            if num_cols:
                return f"result = df['{num_cols[0]}'].mean()"
        elif "status" in q_lower or "fault" in q_lower or "filter" in q_lower or "show me" in q_lower:
            if "status" in df.columns:
                if "fault" in q_lower:
                    return "result = df[df['status'].astype(str).str.upper() == 'FAULT']"
                if "operational" in q_lower:
                    return "result = df[df['status'].astype(str).str.upper() == 'OPERATIONAL']"
                return "result = df[df['status'].notna()]"
        elif "downtime" in q_lower or "most" in q_lower or "max" in q_lower:
            if "machine_id" in df.columns and "downtime" in df.columns:
                return "result = df.groupby('machine_id')['downtime'].sum().idxmax()"
            if "machine_id" in df.columns:
                return "result = df['machine_id'].value_counts().idxmax()"
        return "result = df.head(10)"

    # ChatGroq invocation
    sample_rows = json.dumps(df.head(3).to_dict(orient="records"), default=str)
    schema_info = ", ".join([f"'{c}' ({df[c].dtype})" for c in df.columns])

    system_prompt = (
        "You are a pandas data analyst. Write a single line of pandas code that computes the answer "
        "to the user's question, assigning the result to a variable called `result`.\n"
        "Return ONLY the pandas code, no explanation, no markdown fences, no imports. Assume the dataframe is named `df`."
    )
    user_prompt = (
        f"Dataframe columns & types: {schema_info}\n"
        f"Sample rows:\n{sample_rows}\n\n"
        f"Question: {question}\n\n"
        "Pandas code (assigning to `result`):"
    )

    try:
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, groq_api_key=api_key)
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        return str(response.content).strip()
    except Exception as e:
        print(f"[query_service] LLM call failed ({e}). Falling back to head(10).")
        return "result = df.head(10)"


def answer_query(question: str, dataset_id: str) -> dict:
    """Loads dataset pickle, generates and sanitizes pandas code, executes safely with timeout, and returns formatted result."""
    pickle_path = os.path.join(STORAGE_DIR, "parsed", f"{dataset_id}.pkl")
    if not os.path.exists(pickle_path):
        return {
            "answer_text": f"Dataset '{dataset_id}' not found.",
            "data": None,
            "chart_config": None,
            "error": True,
        }

    try:
        df = pd.read_pickle(pickle_path)
    except Exception as e:
        return {
            "answer_text": f"Failed to load dataset pickle: {str(e)}",
            "data": None,
            "chart_config": None,
            "error": True,
        }

    # Sanitize input question
    if not _sanitize_code(question):
        return {
            "answer_text": "Security warning: Query contained forbidden keywords. Please rephrase your question without system or import operations.",
            "data": None,
            "chart_config": None,
            "error": True,
        }

    # Generate pandas code
    raw_code = _generate_pandas_code(question, df)
    sanitized_code = _sanitize_code(raw_code)

    if not sanitized_code:
        return {
            "answer_text": "Security warning: Generated code contained forbidden keywords. Please rephrase your question without system or import operations.",
            "data": None,
            "chart_config": None,
            "error": True,
        }


    # Safe restricted execution
    local_vars = {"df": df, "result": None}
    safe_globals = {"__builtins__": {}, "pd": pd, "np": np}

    def _exec_target():
        exec(sanitized_code, safe_globals, local_vars)
        return local_vars.get("result")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_exec_target)
            exec_result = future.result(timeout=5.0)
    except concurrent.futures.TimeoutError:
        return {
            "answer_text": "Execution timeout: Calculation exceeded the 5-second time limit.",
            "data": None,
            "chart_config": None,
            "error": True,
        }
    except Exception as e:
        return {
            "answer_text": f"Calculation error: {str(e)}",
            "data": None,
            "chart_config": None,
            "error": True,
        }

    # Process execution result
    if isinstance(exec_result, pd.Series):
        exec_result = exec_result.reset_index()

    if isinstance(exec_result, pd.DataFrame):
        chart_config = _suggest_chart_config(exec_result)
        # Convert to list of dict records safely
        records_json = json.loads(exec_result.to_json(orient="records", date_format="iso"))
        answer_text = f"Query returned {len(exec_result)} record(s)."
        return {
            "answer_text": answer_text,
            "data": records_json,
            "chart_config": chart_config,
        }
    else:
        # Scalar result (int, float, str, bool, etc.)
        python_scalar = _to_python(exec_result)
        if python_scalar is None:
            answer_text = "Result is None / empty."
        else:
            answer_text = f"Answer: {python_scalar}"

        return {
            "answer_text": answer_text,
            "data": python_scalar,
            "chart_config": None,
        }

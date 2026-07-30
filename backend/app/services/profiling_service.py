import math
import warnings
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

import pandas as pd
from sklearn.ensemble import IsolationForest
try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

INDUSTRIAL_KEYWORDS = [
    "temp",
    "temperature",
    "pressure",
    "vibration",
    "rpm",
    "speed",
    "downtime",
    "status",
    "fault",
    "error",
    "alarm",
    "voltage",
    "current",
    "flow",
]


def _to_python(val: Any) -> Any:
    """Helper to convert numpy/pandas scalars to native Python types."""
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
    return val


def classify_dtype(series: pd.Series) -> str:
    """Classifies a Pandas series into numeric, categorical, datetime, text, or boolean."""
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    # Check for object or string dtypes
    if series.dtype == "object" or isinstance(series.dtype, pd.StringDtype):
        non_nulls = series.dropna().astype(str)
        if len(non_nulls) > 0:
            # Try to infer datetime sample
            try:
                sample = non_nulls.head(20)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    parsed = pd.to_datetime(sample, errors="coerce")
                if parsed.notna().sum() > 0.8 * len(sample):
                    return "datetime"
            except Exception:
                pass


            n_unique = non_nulls.nunique()
            # If unique count is small relative to dataset, classify as categorical
            if n_unique <= min(50, max(5, int(0.2 * len(series)))):
                return "categorical"
            return "text"
        return "categorical"

    return "categorical"


def compute_entity_rollup(df: pd.DataFrame, profile: dict) -> dict | None:
    """
    Computes per-machine/entity rollup for operational risk assessment.
    Returns a dict with entity column, entities list, and summary counts.
    Returns None if no suitable entity column is found.
    """
    # 1. Auto-detect entity column
    entity_candidates = []
    for col in df.columns:
        col_lower = str(col).lower()
        if any(kw in col_lower for kw in ["machine", "equipment", "asset", "device", "unit", "id"]):
            # Check if categorical with reasonable cardinality
            if df[col].dtype == "object" or isinstance(df[col].dtype, pd.StringDtype):
                unique_count = df[col].nunique()
                if 2 <= unique_count <= 500:
                    entity_candidates.append((col, unique_count))
            # Also consider numeric IDs if they are actually categorical (low cardinality)
            elif pd.api.types.is_numeric_dtype(df[col]):
                unique_count = df[col].nunique()
                if 2 <= unique_count <= 500:
                    entity_candidates.append((col, unique_count))

    if not entity_candidates:
        return None

    # Select the candidate with the highest cardinality (or first? spec says reasonable number, we'll take first)
    entity_col, _ = entity_candidates[0]

    # 2. Prepare data needed for rollup
    anomalies = profile.get("anomalies")
    industrial_signals = profile.get("industrial_signals", {})

    # Get anomaly row indices if available
    anomaly_indices = set()
    if anomalies and isinstance(anomalies.get("anomalous_row_indices"), list):
        anomaly_indices = set(anomalies["anomalous_row_indices"])

    # Get threshold breach counts per column from industrial_signals
    # We'll compute per entity by checking each row's value against the 3-sigma threshold stored in industrial_signals
    # For each column in industrial_signals, we have mean and std (we stored them above)
    column_thresholds = {}
    for col_name, signal_info in industrial_signals.items():
        if col_name in df.columns and pd.api.types.is_numeric_dtype(df[col_name]):
            mean_val = signal_info.get("mean")
            std_val = signal_info.get("std")
            if mean_val is not None and std_val is not None and std_val > 0:
                column_thresholds[col_name] = (mean_val, std_val)

    # 3. Group by entity
    grouped = df.groupby(entity_col)
    entities_list = []

    for entity_id, group in grouped:
        entity_id_str = str(entity_id)
        row_count = len(group)

        # anomaly_count: how many rows in this group are in anomaly_indices
        anomaly_count = sum(1 for idx in group.index if idx in anomaly_indices)

        # threshold_breach_count: for each row in group, check if any industrial signal column breaches its 3-sigma threshold
        breach_count = 0
        for col_name, (mean_val, std_val) in column_thresholds.items():
            if col_name in group.columns:
                # Vectorized check for breaches in this column for the group
                series = group[col_name]
                # Avoid division by zero; std_val > 0 already checked
                lower_bound = mean_val - 3 * std_val
                upper_bound = mean_val + 3 * std_val
                # Count values outside [lower_bound, upper_bound]
                breach_count += ((series < lower_bound) | (series > upper_bound)).sum()

        # downtime_total: sum of downtime column if exists
        downtime_total = None
        downtime_col = None
        for col in df.columns:
            if any(kw in str(col).lower() for kw in ["downtime", "down_time", "loss_minutes", "stop_time"]):
                downtime_col = col
                break
        if downtime_col and pd.api.types.is_numeric_dtype(df[downtime_col]):
            downtime_total = float(group[downtime_col].sum())

        # fault_count: count of rows where status/fault/error column indicates fault state
        fault_count = 0
        fault_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(kw in col_lower for kw in ["status", "fault", "error"]):
                fault_col = col
                break
        if fault_col:
            # Check for fault indicators (case-insensitive)
            fault_series = group[fault_col].astype(str).str.lower()
            fault_indicators = ["fault", "error", "down", "alarm", "stopped"]
            fault_count = fault_series.isin(fault_indicators).sum()

        entities_list.append({
            "entity_id": entity_id_str,
            "row_count": int(row_count),
            "anomaly_count": int(anomaly_count),
            "threshold_breach_count": int(breach_count),
            "downtime_total": downtime_total,
            "fault_count": int(fault_count),
        })

    # 4. Assign severity tiers
    for entity in entities_list:
        row_count = entity["row_count"]
        anomaly_count = entity["anomaly_count"]
        fault_count = entity["fault_count"]
        downtime_total = entity["downtime_total"]

        # Calculate downtime threshold for top 25%
        downtime_vals = [e["downtime_total"] for e in entities_list if e["downtime_total"] is not None]
        downtime_top25_threshold = None
        if downtime_vals:
            sorted_downtime = sorted(downtime_vals, reverse=True)
            idx = max(0, int(len(sorted_downtime) * 0.25) - 1)  # top 25% start at index 0, we want the minimum value in top 25%
            if len(sorted_downtime) > 0:
                downtime_top25_threshold = sorted_downtime[idx] if idx < len(sorted_downtime) else sorted_downtime[-1]

        # Escalate condition: anomaly_count > 10% of row_count OR (fault_count > 0 and downtime_total in top 25%)
        escalate = False
        if row_count > 0 and anomaly_count > 0.1 * row_count:
            escalate = True
        elif fault_count > 0 and downtime_total is not None and downtime_top25_threshold is not None:
            if downtime_total >= downtime_top25_threshold:
                escalate = True

        # Watch condition: anomaly_count > 0 OR threshold_breach_count > 0
        watch = (anomaly_count > 0) or (entity["threshold_breach_count"] > 0)

        if escalate:
            entity["severity"] = "escalate"
        elif watch:
            entity["severity"] = "watch"
        else:
            entity["severity"] = "normal"

    # 5. Sort entities: escalate first, then watch, then normal; within same severity, by anomaly_count descending
    def sort_key(entity):
        severity_order = {"escalate": 0, "watch": 1, "normal": 2}
        return (severity_order[entity["severity"]], -entity["anomaly_count"])

    entities_list.sort(key=sort_key)

    # 6. Summary counts
    total_entities = len(entities_list)
    escalate_count = sum(1 for e in entities_list if e["severity"] == "escalate")
    watch_count = sum(1 for e in entities_list if e["severity"] == "watch")
    normal_count = sum(1 for e in entities_list if e["severity"] == "normal")

    return {
        "entity_column": entity_col,
        "entities": entities_list,
        "summary": {
            "total_entities": total_entities,
            "escalate_count": escalate_count,
            "watch_count": watch_count,
            "normal_count": normal_count,
        }
    }


def compute_eda(df: pd.DataFrame) -> dict:
    """
    Performs exploratory data analysis and returns a dictionary with the results.
    Includes missing data statistics, outlier detection via Isolation Forest, and correlations.
    """
    # Handle empty DataFrame
    if df is None or df.empty:
        return {
            "missing_data": {
                "total_cells": 0,
                "total_missing": 0,
                "missing_percentage": 0.0,
                "columns_missing_count": {},
                "columns_missing_percentage": {}
            },
            "outlier_detection": {
                "method": "isolation_forest",
                "anomalous_row_count": 0,
                "anomalous_row_pct": 0.0,
                "anomalous_row_indices": []
            },
            "correlations": []
        }

    rows, cols = df.shape
    total_cells = rows * cols

    # Missing data statistics
    missing_per_column = df.isna().sum()
    total_missing = missing_per_column.sum()
    missing_percentage = (total_missing / total_cells * 100) if total_cells > 0 else 0.0

    columns_missing_count = {col: int(missing_per_column[col]) for col in df.columns}
    columns_missing_percentage = {
        col: float(round((missing_per_column[col] / rows * 100), 2)) if rows > 0 else 0.0
        for col in df.columns
    }

    missing_data_info = {
        "total_cells": int(total_cells),
        "total_missing": int(total_missing),
        "missing_percentage": float(round(missing_percentage, 2)),
        "columns_missing_count": columns_missing_count,
        "columns_missing_percentage": columns_missing_percentage
    }

    # Outlier detection using Isolation Forest (similar to the existing code in profile_dataset)
    # We'll use the same parameters: contamination=0.05, random_state=42, n_jobs=-1
    # Sample max 5000 rows for fitting, predict on max 10000 rows.
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    # We need at least 2 numeric columns for Isolation Forest to work meaningfully
    outlier_info = {
        "method": "isolation_forest",
        "anomalous_row_count": 0,
        "anomalous_row_pct": 0.0,
        "anomalous_row_indices": []
    }

    if len(numeric_cols) >= 2:
        # Drop rows with NaN in numeric columns for the outlier detection
        clean_num_df = df[numeric_cols].dropna()
        if len(clean_num_df) >= 5:
            try:
                # Sample max 5000 rows for fitting
                fit_df = clean_num_df.sample(n=min(5000, len(clean_num_df)), random_state=42)
                from sklearn.ensemble import IsolationForest
                clf = IsolationForest(contamination=0.05, random_state=42, n_jobs=-1)
                clf.fit(fit_df)

                # Predict on top 10000 rows
                predict_df = clean_num_df.head(10000)
                preds = clf.predict(predict_df)
                anomalous_mask = preds == -1
                anomalous_count = int(anomalous_mask.sum())
                anomalous_pct = float(round((anomalous_count / len(predict_df)) * 100, 2))
                anomalous_indices = [int(idx) for idx in predict_df.index[anomalous_mask].tolist()[:50]]

                outlier_info = {
                    "method": "isolation_forest",
                    "anomalous_row_count": anomalous_count,
                    "anomalous_row_pct": anomalous_pct,
                    "anomalous_row_indices": anomalous_indices
                }
            except Exception as e:
                # If anything goes wrong, we leave outlier_info as zeros/empty but we could add a warning?
                # Since we are not modifying the existing warnings, we just leave it.
                pass
        # else: not enough non-null numeric rows, leave as default
    # else: less than 2 numeric columns, leave as default

    # Correlations
    correlations_info = []
    valid_numeric_cols = [c for c in numeric_cols if df[c].dropna().nunique() > 1]
    if len(valid_numeric_cols) >= 2:
        try:
            corr_matrix = df[valid_numeric_cols].corr(numeric_only=True)
            for i in range(len(valid_numeric_cols)):
                for j in range(i + 1, len(valid_numeric_cols)):
                    col_a = valid_numeric_cols[i]
                    col_b = valid_numeric_cols[j]
                    val = corr_matrix.loc[col_a, col_b]
                    if not pd.isna(val):
                        correlations_info.append({
                            "col_a": col_a,
                            "col_b": col_b,
                            "correlation": float(round(val, 4)),
                            "is_strong": bool(abs(val) > 0.7)
                        })
            correlations_info.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        except Exception as e:
            pass
    # else: less than 2 valid numeric columns, leave as empty list

    return {
        "missing_data": missing_data_info,
        "outlier_detection": outlier_info,
        "correlations": correlations_info
    }


def profile_dataset(df: pd.DataFrame) -> dict:
    """Analyzes a Pandas DataFrame and returns a comprehensive, JSON-serializable profiling dict."""
    warnings: List[str] = []

    # Handle empty DataFrame
    if df is None or df.empty:
        return {
            "shape": {"rows": 0, "columns": 0},
            "memory_usage_mb": 0.0,
            "columns": [],
            "correlations": [],
            "anomalies": None,
            "industrial_signals": {},
            "warnings": ["DataFrame is empty or None."],
        }

    rows, cols = df.shape
    memory_mb = float(round(df.memory_usage(deep=True).sum() / (1024 * 1024), 4))

    column_profiles: List[Dict[str, Any]] = []
    numeric_cols: List[str] = []

    for col in df.columns:
        series = df[col]
        dtype_category = classify_dtype(series)
        missing_count = int(series.isna().sum())
        missing_pct = float(round((missing_count / rows) * 100, 2)) if rows > 0 else 0.0

        col_profile: Dict[str, Any] = {
            "name": str(col),
            "dtype": dtype_category,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
        }

        s_clean = series.dropna()
        if len(s_clean) == 0:
            warnings.append(f"Column '{col}' contains only NaN/null values.")

        if dtype_category == "numeric":
            numeric_cols.append(str(col))
            if len(s_clean) > 0:
                q1 = float(s_clean.quantile(0.25))
                q3 = float(s_clean.quantile(0.75))
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                outliers = int(((s_clean < lower_bound) | (s_clean > upper_bound)).sum())

                col_profile.update({
                    "mean": _to_python(round(s_clean.mean(), 4)),
                    "median": _to_python(round(s_clean.median(), 4)),
                    "std": _to_python(round(s_clean.std(), 4)) if len(s_clean) > 1 else 0.0,
                    "min": _to_python(s_clean.min()),
                    "max": _to_python(s_clean.max()),
                    "q1": _to_python(round(q1, 4)),
                    "q3": _to_python(round(q3, 4)),
                    "outlier_count": outliers,
                })
            else:
                col_profile.update({
                    "mean": None,
                    "median": None,
                    "std": None,
                    "min": None,
                    "max": None,
                    "q1": None,
                    "q3": None,
                    "outlier_count": 0,
                })

        elif dtype_category in ("categorical", "text", "boolean"):
            unique_cnt = int(series.nunique(dropna=True))
            top_5 = []
            val_counts = series.value_counts(dropna=False).head(5)
            for val, cnt in val_counts.items():
                val_str = "NaN" if pd.isna(val) else str(val)
                top_5.append({"value": val_str, "count": int(cnt)})

            col_profile.update({
                "unique_count": unique_cnt,
                "top_5_values": top_5,
            })

        elif dtype_category == "datetime":
            dt_series = pd.to_datetime(series, errors="coerce").dropna()
            if len(dt_series) > 0:
                min_date = dt_series.min().isoformat()
                max_date = dt_series.max().isoformat()
                inferred_freq = None
                gap_count = 0

                if len(dt_series) >= 3:
                    try:
                        sorted_dt = dt_series.sort_values()
                        inferred_freq = pd.infer_freq(sorted_dt)
                        if inferred_freq:
                            full_range = pd.date_range(
                                start=sorted_dt.iloc[0],
                                end=sorted_dt.iloc[-1],
                                freq=inferred_freq,
                            )
                            gap_count = max(0, len(full_range) - len(sorted_dt.unique()))
                    except Exception as e:
                        warnings.append(f"Could not calculate datetime gaps for column '{col}': {str(e)}")

                col_profile.update({
                    "min_date": min_date,
                    "max_date": max_date,
                    "inferred_frequency": inferred_freq,
                    "gap_count": int(gap_count),
                })
            else:
                col_profile.update({
                    "min_date": None,
                    "max_date": None,
                    "inferred_frequency": None,
                    "gap_count": 0,
                })

        column_profiles.append(col_profile)

    # 1. Correlations for numeric column pairs
    correlations: List[Dict[str, Any]] = []
    valid_numeric_cols = [c for c in numeric_cols if df[c].dropna().nunique() > 1]

    if len(valid_numeric_cols) >= 2:
        try:
            corr_matrix = df[valid_numeric_cols].corr(numeric_only=True)
            for i in range(len(valid_numeric_cols)):
                for j in range(i + 1, len(valid_numeric_cols)):
                    col_a = valid_numeric_cols[i]
                    col_b = valid_numeric_cols[j]
                    val = corr_matrix.loc[col_a, col_b]
                    if not pd.isna(val):
                        correlations.append({
                            "col_a": col_a,
                            "col_b": col_b,
                            "correlation": float(round(val, 4)),
                            "is_strong": bool(abs(val) > 0.7),
                        })
            correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        except Exception as e:
            warnings.append(f"Correlation calculation failed: {str(e)}")
    elif len(numeric_cols) < 2:
        warnings.append("Fewer than 2 numeric columns available for correlation analysis.")

    # 2. Anomalies using Isolation Forest (sampled for fast performance)
    anomalies: Optional[Dict[str, Any]] = None
    if len(valid_numeric_cols) >= 2:
        clean_num_df = df[valid_numeric_cols].dropna()
        if len(clean_num_df) >= 5:
            try:
                # Sample max 5000 rows for Isolation Forest fit to run in under 0.1s
                fit_df = clean_num_df.sample(n=min(5000, len(clean_num_df)), random_state=42)
                clf = IsolationForest(contamination=0.05, random_state=42, n_jobs=-1)
                clf.fit(fit_df)
                
                # Predict on top 10000 rows
                predict_df = clean_num_df.head(10000)
                preds = clf.predict(predict_df)
                anomalous_mask = preds == -1
                anomalous_count = int(anomalous_mask.sum())
                anomalous_pct = float(round((anomalous_count / len(predict_df)) * 100, 2))
                anomalous_indices = [int(idx) for idx in predict_df.index[anomalous_mask].tolist()[:50]]

                anomalies = {
                    "method": "isolation_forest",
                    "anomalous_row_count": anomalous_count,
                    "anomalous_row_pct": anomalous_pct,
                    "anomalous_row_indices": anomalous_indices,
                }
            except Exception as e:
                warnings.append(f"Isolation Forest anomaly detection failed: {str(e)}")
        else:
            warnings.append("Fewer than 5 non-null numeric rows available for Isolation Forest anomaly detection.")
    else:
        warnings.append("Fewer than 2 numeric columns available for anomaly detection.")


    # 3. Industrial Signals Detection
    industrial_signals: Dict[str, Any] = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if any(kw in col_lower for kw in INDUSTRIAL_KEYWORDS):
            if pd.api.types.is_numeric_dtype(df[col]):
                s_clean = df[col].dropna()
                if len(s_clean) >= 3:
                    mean_val = float(s_clean.mean())
                    std_val = float(s_clean.std())
                    if std_val > 0:
                        breaches = s_clean[abs(s_clean - mean_val) > 3 * std_val]
                        breach_cnt = int(len(breaches))
                        breach_pct = float(round((breach_cnt / len(s_clean)) * 100, 2))
                        sample_vals = [_to_python(v) for v in breaches.head(10).tolist()]

                        industrial_signals[str(col)] = {
                            "mean": mean_val,
                            "std": std_val,
                            "threshold_breach_count": breach_cnt,
                            "threshold_breach_pct": breach_pct,
                            "sample_breach_values": sample_vals,
                        }
                    else:
                        industrial_signals[str(col)] = {
                            "mean": mean_val,
                            "std": std_val,
                            "threshold_breach_count": 0,
                            "threshold_breach_pct": 0.0,
                            "sample_breach_values": [],
                        }

    # 4. Operator & Machine Entity Rollup (Problem Child & Financial Impact)
    machine_col = None
    for c in df.columns:
        if any(kw in str(c).lower() for kw in ["machine", "asset", "equipment", "unit_id", "device_id", "mc_id"]):
            machine_col = c
            break

    downtime_col = None
    for c in df.columns:
        if any(kw in str(c).lower() for kw in ["downtime", "down_time", "loss_minutes", "stop_time"]):
            downtime_col = c
            break

    machine_breakdown = []
    problem_child_machine = None
    total_downtime_mins = 0.0
    total_loss_inr = 0.0

    if machine_col is not None:
        try:
            grouped = df.groupby(machine_col)
            for m_id, group in grouped:
                m_str = str(m_id)
                rec_cnt = len(group)
                dt_mins = float(group[downtime_col].sum()) if (downtime_col and pd.api.types.is_numeric_dtype(group[downtime_col])) else 0.0
                total_downtime_mins += dt_mins

                # Financial loss estimate at ₹500/min ($6/min) baseline production cost
                loss_inr = round(dt_mins * 500.0, 2)
                total_loss_inr += loss_inr

                # Severity logic
                if dt_mins > 60:
                    sev = "CRITICAL"
                elif dt_mins > 10:
                    sev = "WARNING"
                else:
                    sev = "HEALTHY"

                machine_breakdown.append({
                    "machine_id": m_str,
                    "record_count": rec_cnt,
                    "downtime_minutes": round(dt_mins, 1),
                    "downtime_hours": round(dt_mins / 60.0, 2),
                    "est_financial_loss_inr": loss_inr,
                    "severity": sev,
                })

            # Sort by highest downtime / financial loss descending to identify Problem Child
            machine_breakdown.sort(key=lambda x: (x["downtime_minutes"], x["record_count"]), reverse=True)
            if machine_breakdown:
                problem_child_machine = machine_breakdown[0]["machine_id"]
        except Exception as e:
            warnings.append(f"Machine entity rollup calculation failed: {str(e)}")
    else:
        # Fallback if no machine_col exists: calculate global downtime if downtime_col is present
        if downtime_col and pd.api.types.is_numeric_dtype(df[downtime_col]):
            total_downtime_mins = float(df[downtime_col].sum())
            total_loss_inr = round(total_downtime_mins * 500.0, 2)

    # Determine Plant Health Status & Urgency Tier
    anom_cnt = anomalies.get("anomalous_row_count", 0) if anomalies else 0
    if total_downtime_mins > 120 or anom_cnt > 10:
        overall_status = "CRITICAL ACTION REQUIRED"
        urgency_tier = "HIGH"
    elif total_downtime_mins > 30 or anom_cnt > 0:
        overall_status = "ELEVATED RISK / WATCH LIST"
        urgency_tier = "MEDIUM"
    else:
        overall_status = "NORMAL OPERATIONAL PARAMETERS"
        urgency_tier = "LOW"

    plant_executive_summary = {
        "overall_status": overall_status,
        "urgency_tier": urgency_tier,
        "problem_child_machine": problem_child_machine or "N/A",
        "total_downtime_minutes": round(total_downtime_mins, 1),
        "total_downtime_hours": round(total_downtime_mins / 60.0, 2),
        "total_est_loss_inr": total_loss_inr,
        "total_est_loss_usd": round(total_loss_inr / 83.0, 2),
    }

    # Extract sample rows for telemetry charts & visualization
    sample_df = df.head(50).copy()
    sample_rows = []
    for _, row in sample_df.iterrows():
        row_dict = {str(k): _to_python(v) for k, v in row.items()}
        sample_rows.append(row_dict)

    # 5. Entity Rollup for Operational Risk
    entity_rollup = compute_entity_rollup(df, {
        "anomalies": anomalies,
        "industrial_signals": industrial_signals,
    })

    eda_result = compute_eda(df)
    return {
        "shape": {"rows": int(rows), "columns": int(cols)},
        "memory_usage_mb": memory_mb,
        "columns": column_profiles,
        "correlations": correlations,
        "anomalies": anomalies,
        "industrial_signals": industrial_signals,
        "sample_rows": sample_rows,
        "machine_breakdown": machine_breakdown,
        "plant_executive_summary": plant_executive_summary,
        "warnings": warnings,
        "entity_rollup": entity_rollup,
        "eda": eda_result,
    }



import math
import warnings
from typing import Any, Dict, List, Optional
import numpy as np

import pandas as pd
from sklearn.ensemble import IsolationForest

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
                            "threshold_breach_count": breach_cnt,
                            "threshold_breach_pct": breach_pct,
                            "sample_breach_values": sample_vals,
                        }
                    else:
                        industrial_signals[str(col)] = {
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
    }



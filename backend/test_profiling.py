import json
import numpy as np
import pandas as pd
from app.services.profiling_service import profile_dataset


def run_test():
    print("Generating sample industrial dataset...")
    np.random.seed(42)

    timestamps = pd.date_range("2026-07-27 00:00", periods=100, freq="15min")
    machine_ids = np.random.choice(["MCH-101", "MCH-102", "MCH-103"], size=100)

    # Base signals with strong correlation between temperature and pressure
    temp_base = np.random.normal(loc=75.0, scale=5.0, size=100)
    pressure_base = temp_base * 1.5 + np.random.normal(loc=10.0, scale=1.0, size=100)
    vibration_base = np.random.normal(loc=0.5, scale=0.1, size=100)

    # Inject extreme industrial breach values & outliers
    temp_base[10] = 120.0  # 3-sigma breach
    pressure_base[10] = 200.0  # breach
    vibration_base[25] = 4.5  # anomaly breach

    statuses = np.random.choice(["OPERATIONAL", "MAINTENANCE", "FAULT"], size=100, p=[0.85, 0.10, 0.05])

    df = pd.DataFrame({
        "timestamp": timestamps,
        "machine_id": machine_ids,
        "temperature": temp_base,
        "pressure": pressure_base,
        "vibration": vibration_base,
        "status": statuses,
    })

    print(f"Sample dataset shape: {df.shape}")
    print("\nRunning profile_dataset()...")
    result = profile_dataset(df)

    # Verify JSON serializability
    json_str = json.dumps(result, indent=2)
    print("\n--- PROFILING RESULT SUMMARY ---")
    print(f"Shape: {result['shape']}")
    print(f"Memory Usage: {result['memory_usage_mb']} MB")
    print(f"Columns Count: {len(result['columns'])}")
    print(f"Correlations Found: {len(result['correlations'])}")
    if result["correlations"]:
        print(f"Top Correlation: {result['correlations'][0]}")
    if result["anomalies"]:
        print(f"Anomalies Count: {result['anomalies']['anomalous_row_count']} ({result['anomalies']['anomalous_row_pct']}%)")
    print(f"Industrial Signals Keys: {list(result['industrial_signals'].keys())}")
    for k, v in result['industrial_signals'].items():
        print(f"  Signal {k}: {v['threshold_breach_count']} breach(es)")
    print(f"Warnings: {result['warnings']}")

    print("\nFull JSON string output length:", len(json_str))
    print("SUCCESS: profile_dataset() runs smoothly and produces valid JSON!")


if __name__ == "__main__":
    run_test()

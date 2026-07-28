import io
import json
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app


def test_report_pipeline_end_to_end():
    print("Testing LangGraph Report Pipeline & API Endpoints...")
    client = TestClient(app)

    # 1. Generate sample dataset
    np.random.seed(42)
    timestamps = pd.date_range("2026-07-27 00:00", periods=50, freq="15min").astype(str)
    machines = np.random.choice(["TURBINE-01", "TURBINE-02"], size=50)
    temp = np.random.normal(80, 5, 50)
    press = temp * 1.8 + np.random.normal(5, 1, 50)
    temp[5] = 135.0  # breach
    press[5] = 250.0  # breach

    df = pd.DataFrame({
        "timestamp": timestamps,
        "machine_id": machines,
        "temperature": temp,
        "pressure": press,
        "status": ["NORMAL"] * 48 + ["CRITICAL"] * 2,
    })

    csv_bytes = df.to_csv(index=False).encode("utf-8")

    # 2. Upload dataset via POST /upload
    files = {"file": ("plant_telemetry.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_res = client.post("/upload", files=files)
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    upload_data = upload_res.json()
    dataset_id = upload_data["dataset_id"]
    print(f"[OK] Uploaded test dataset (ID: {dataset_id})")

    # 3. Generate report via POST /datasets/{dataset_id}/report
    print("\nCalling POST /datasets/{dataset_id}/report (running LangGraph StateGraph)...")
    report_res = client.post(f"/datasets/{dataset_id}/report")
    assert report_res.status_code == 200, f"Report generation failed: {report_res.text}"
    report = report_res.json()
    print("[OK] POST /datasets/{dataset_id}/report returned 200 OK")

    # 4. Verify all required keys in report
    required_keys = ["overview", "schema_summary", "data_quality", "key_trends", "anomalies", "recommendations", "raw_profile_reference"]
    for key in required_keys:
        assert key in report, f"Missing required key '{key}' in report output!"

    assert isinstance(report["recommendations"], list)
    assert len(report["recommendations"]) >= 1
    assert isinstance(report["data_quality"], dict)
    assert len(report["data_quality"]) == 5

    print("[OK] All required report keys & data quality structures present.")

    # 5. Fetch report via GET /datasets/{dataset_id}/report
    fetch_res = client.get(f"/datasets/{dataset_id}/report")
    assert fetch_res.status_code == 200
    fetched_report = fetch_res.json()
    assert fetched_report["schema_summary"] == report["schema_summary"]
    print("[OK] GET /datasets/{dataset_id}/report matched generated report.")

    # 6. Print Report Sections
    print("\n" + "=" * 60)
    print("                GENERATED INDUSTRIAL REPORT                ")
    print("=" * 60)
    print(f"\n[SCHEMA SUMMARY]\n{report['schema_summary']}\n")
    print(f"[OVERVIEW NARRATIVE]\n{report['overview']}\n")
    print(f"[DATA QUALITY SUMMARY]\n{json.dumps(report['data_quality'], indent=2)}\n")
    print(f"[KEY TRENDS & CORRELATIONS]\n{report['key_trends']}\n")
    print(f"[ANOMALIES & SIGNALS]\n{report['anomalies']}\n")
    print(f"[RECOMMENDATIONS]\n" + "\n".join([f"  • {r}" for r in report['recommendations']]) + "\n")
    print("=" * 60)

    print("\nSUCCESS: LangGraph report pipeline & report API endpoints verified end-to-end!")


if __name__ == "__main__":
    test_report_pipeline_end_to_end()

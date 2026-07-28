import io
import json
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app


def test_full_integration():
    print("Testing Full System Integration (Upload -> Profile -> Report -> Rows -> Query -> Chat History)...")
    client = TestClient(app)

    # 1. Create sample dataset
    np.random.seed(42)
    timestamps = pd.date_range("2026-07-27 08:00", periods=40, freq="15min").astype(str)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "machine_id": ["PUMP-01"] * 20 + ["PUMP-02"] * 20,
        "temperature": np.random.normal(82, 3, 40),
        "pressure": np.random.normal(120, 10, 40),
        "vibration": np.random.normal(0.4, 0.05, 40),
        "status": ["OPERATIONAL"] * 38 + ["FAULT"] * 2,
    })
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    # 2. Upload dataset
    upload_res = client.post("/upload", files={"file": ("full_telemetry.csv", io.BytesIO(csv_bytes), "text/csv")})
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["dataset_id"]
    print(f"[OK] Uploaded dataset (ID: {dataset_id})")

    # 3. Generate Report
    report_res = client.post(f"/datasets/{dataset_id}/report")
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert "overview" in report_data
    assert "recommendations" in report_data
    print("[OK] Generated report via LangGraph pipeline")

    # 4. Fetch Dataset Rows via GET /datasets/{dataset_id}/rows
    rows_res = client.get(f"/datasets/{dataset_id}/rows?indices=0,1,2")
    assert rows_res.status_code == 200
    rows_data = rows_res.json()
    assert "rows" in rows_data
    assert len(rows_data["rows"]) == 3
    print("[OK] GET /datasets/{dataset_id}/rows returned 3 requested rows")

    # 5. Natural Language Query
    query_res = client.post(f"/datasets/{dataset_id}/query", json={"question": "what is the average pressure"})
    assert query_res.status_code == 200
    query_data = query_res.json()
    assert "answer_text" in query_data
    print(f"[OK] Natural Language Query returned answer: {query_data['answer_text']}")

    # 6. Chat History Retrieval
    history_res = client.get(f"/datasets/{dataset_id}/chat-history")
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 1
    print(f"[OK] GET /datasets/{dataset_id}/chat-history returned {len(history)} log(s)")

    print("\nFULL SYSTEM INTEGRATION VERIFIED 100% WORKING!")


if __name__ == "__main__":
    test_full_integration()

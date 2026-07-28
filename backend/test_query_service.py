import io
import json
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app


def test_query_service_and_endpoints():
    print("Testing Natural Language Query Service & Security Sanitizer...")
    client = TestClient(app)

    # 1. Prepare sample dataset
    np.random.seed(42)
    timestamps = pd.date_range("2026-07-27 00:00", periods=30, freq="10min").astype(str)
    machines = np.random.choice(["PUMP-01", "PUMP-02", "PUMP-03"], size=30)
    temps = np.random.normal(85, 4, 30)
    downtimes = np.array([0, 15, 0, 45, 0, 120, 0, 0, 10, 0] * 3)
    statuses = ["OPERATIONAL"] * 25 + ["FAULT"] * 5

    df = pd.DataFrame({
        "timestamp": timestamps,
        "machine_id": machines,
        "temperature": temps,
        "downtime": downtimes,
        "status": statuses,
    })

    csv_bytes = df.to_csv(index=False).encode("utf-8")

    # 2. Upload dataset via POST /upload
    files = {"file": ("query_test_data.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_res = client.post("/upload", files=files)
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["dataset_id"]
    print(f"[OK] Uploaded dataset for querying (ID: {dataset_id})")

    # 3. Test Question 1: "what is the average temperature"
    print("\nTesting Query 1: 'what is the average temperature'...")
    q1_res = client.post(f"/datasets/{dataset_id}/query", json={"question": "what is the average temperature"})
    assert q1_res.status_code == 200, f"Query 1 failed: {q1_res.text}"
    q1_data = q1_res.json()
    assert "answer_text" in q1_data
    assert q1_data["data"] is not None
    print(f"[OK] Query 1 Result: {q1_data['answer_text']} (Value: {q1_data['data']})")

    # 4. Test Question 2: "show me rows where status is fault"
    print("\nTesting Query 2: 'show me rows where status is fault'...")
    q2_res = client.post(f"/datasets/{dataset_id}/query", json={"question": "show me rows where status is fault"})
    assert q2_res.status_code == 200, f"Query 2 failed: {q2_res.text}"
    q2_data = q2_res.json()
    assert isinstance(q2_data["data"], list)
    assert len(q2_data["data"]) == 5
    assert q2_data["chart_config"] is not None
    print(f"[OK] Query 2 Result: Returned {len(q2_data['data'])} FAULT record(s) with chart_config: {q2_data['chart_config']}")

    # 5. Test Question 3: "which machine had the most downtime"
    print("\nTesting Query 3: 'which machine had the most downtime'...")
    q3_res = client.post(f"/datasets/{dataset_id}/query", json={"question": "which machine had the most downtime"})
    assert q3_res.status_code == 200, f"Query 3 failed: {q3_res.text}"
    q3_data = q3_res.json()
    print(f"[OK] Query 3 Result: {q3_data['answer_text']}")

    # 6. Test Security Sanitization: Malicious query attempt
    print("\nTesting Security Sanitizer on malicious code injection: 'import os; os.system(\"ls\")'...")
    malicious_query = "import os; os.system('ls')"
    mal_res = client.post(f"/datasets/{dataset_id}/query", json={"question": malicious_query})
    assert mal_res.status_code == 200
    mal_data = mal_res.json()
    assert mal_data.get("error") is True
    assert "Security warning" in mal_data["answer_text"]
    print(f"[OK] Security Sanitizer successfully BLOCKED malicious code: '{mal_data['answer_text']}'")

    # 7. Test GET /datasets/{dataset_id}/chat-history
    print("\nTesting GET /datasets/{dataset_id}/chat-history...")
    history_res = client.get(f"/datasets/{dataset_id}/chat-history")
    assert history_res.status_code == 200
    history = history_res.json()
    assert isinstance(history, list)
    assert len(history) == 4  # 3 valid queries + 1 blocked attempt logged
    print(f"[OK] GET /datasets/{dataset_id}/chat-history returned {len(history)} recorded Q&A log(s).")

    print("\nSUCCESS: All query service features, safe sandbox execution, security sanitizer, and chat history endpoints verified!")


if __name__ == "__main__":
    test_query_service_and_endpoints()

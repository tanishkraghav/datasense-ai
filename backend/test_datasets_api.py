import io
import json
import os
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app


def test_endpoints():
    print("Testing Dataset End-to-End API via FastAPI TestClient...")
    client = TestClient(app)

    # 1. Test GET /health
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json() == {"status": "ok"}
    print("[OK] GET /health PASSED")


    # 2. Prepare sample CSV dataset
    df_sample = pd.DataFrame({
        "timestamp": pd.date_range("2026-07-27", periods=20, freq="h").astype(str),
        "machine_id": ["MCH-01"] * 20,
        "temperature": [70 + i * 0.5 for i in range(20)],
        "pressure": [100 + i * 1.0 for i in range(20)],
        "vibration": [0.2 + (0.01 if i % 2 == 0 else -0.01) for i in range(20)],
        "status": ["OK"] * 18 + ["ALERT"] * 2,
    })

    csv_bytes = df_sample.to_csv(index=False).encode("utf-8")

    # 3. Test POST /upload
    files = {"file": ("test_industrial_data.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_res = client.post("/upload", files=files)
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    upload_data = upload_res.json()

    dataset_id = upload_data.get("dataset_id")
    assert dataset_id is not None
    assert upload_data["filename"] == "test_industrial_data.csv"
    assert upload_data["row_count"] == 20
    assert upload_data["col_count"] == 6
    assert upload_data["status"] == "profiled"
    print(f"[OK] POST /upload PASSED (dataset_id: {dataset_id})")

    # 4. Test GET /datasets
    list_res = client.get("/datasets")
    assert list_res.status_code == 200
    datasets_list = list_res.json()
    assert isinstance(datasets_list, list)
    matching = [d for d in datasets_list if d["dataset_id"] == dataset_id]
    assert len(matching) == 1
    assert matching[0]["filename"] == "test_industrial_data.csv"
    print(f"[OK] GET /datasets PASSED (Found {len(datasets_list)} dataset(s))")

    # 5. Test GET /datasets/{dataset_id}/profile
    profile_res = client.get(f"/datasets/{dataset_id}/profile")
    assert profile_res.status_code == 200
    profile = profile_res.json()
    assert profile["shape"] == {"rows": 20, "columns": 6}
    assert len(profile["columns"]) == 6
    print("[OK] GET /datasets/{dataset_id}/profile PASSED")


    # 6. Verify filesystem storage structure
    storage_base = os.path.join(os.path.dirname(__file__), "storage")
    raw_path = os.path.join(storage_base, "datasets", f"{dataset_id}.csv")
    parsed_path = os.path.join(storage_base, "parsed", f"{dataset_id}.pkl")
    profile_path = os.path.join(storage_base, "profiles", f"{dataset_id}.json")
    meta_path = os.path.join(storage_base, "metadata.json")

    assert os.path.exists(raw_path), f"Raw dataset missing at {raw_path}"
    assert os.path.exists(parsed_path), f"Parsed pickle missing at {parsed_path}"
    assert os.path.exists(profile_path), f"Profile JSON missing at {profile_path}"
    assert os.path.exists(meta_path), f"Metadata file missing at {meta_path}"

    print("[OK] Storage verification PASSED (Raw, Pickle, Profile JSON, and Metadata files exist)")


    print("\nALL API ENDPOINTS TESTED AND VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    test_endpoints()

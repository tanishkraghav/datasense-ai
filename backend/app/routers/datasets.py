import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd

from app.core.repository import (
    STORAGE_DIR,
    _ensure_storage_dirs,
    get_dataset_metadata,
    list_all_metadata,
    save_dataset_metadata,
)
from app.services.profiling_service import profile_dataset
from app.services.query_service import answer_query
from app.services.report_pipeline import generate_report


class QueryRequest(BaseModel):
    question: str



router = APIRouter(tags=["datasets"])

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_ROW_COUNT = 500_000
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
@router.post("/datasets/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset(file: UploadFile = File(...)):

    """Uploads a dataset (CSV, XLSX, JSON), validates size and row limits, caches pickle, profiles it, and stores metadata."""
    filename = file.filename or "uploaded_file"
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file content & validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed limit of 50MB ({len(content)} bytes uploaded).",
        )

    # Parse into pandas DataFrame
    try:
        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(content))
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(content))
        elif ext == ".json":
            df = pd.read_json(io.BytesIO(content))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{ext}'.",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file content into DataFrame: {str(e)}",
        )

    # Validate row count
    row_count, col_count = df.shape
    if row_count > MAX_ROW_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset row count ({row_count:,}) exceeds maximum allowed limit of {MAX_ROW_COUNT:,} rows.",
        )

    _ensure_storage_dirs()
    dataset_id = str(uuid.uuid4())

    # 1. Save raw file

    raw_path = os.path.join(STORAGE_DIR, "datasets", f"{dataset_id}{ext}")
    with open(raw_path, "wb") as f:
        f.write(content)

    # 2. Save cached parsed pickle
    pickle_path = os.path.join(STORAGE_DIR, "parsed", f"{dataset_id}.pkl")
    df.to_pickle(pickle_path)

    # 3. Profile dataset
    profile_result = profile_dataset(df)

    # 4. Save profile JSON
    profile_path = os.path.join(STORAGE_DIR, "profiles", f"{dataset_id}.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile_result, f, indent=2)

    # 5. Save metadata repository entry
    created_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "dataset_id": dataset_id,
        "filename": filename,
        "row_count": row_count,
        "col_count": col_count,
        "status": "profiled",
        "created_at": created_at,
    }
    save_dataset_metadata(dataset_id, meta)

    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "row_count": row_count,
        "col_count": col_count,
        "status": "profiled",
    }


@router.get("/datasets", response_class=JSONResponse)
async def get_all_datasets():
    """Lists all uploaded datasets metadata."""
    datasets_list = list_all_metadata()
    return datasets_list


@router.get("/datasets/{dataset_id}/profile", response_class=JSONResponse)
async def get_dataset_profile(dataset_id: str):

    """Returns the raw profile JSON for a given dataset_id."""
    profile_path = os.path.join(STORAGE_DIR, "profiles", f"{dataset_id}.json")
    if not os.path.exists(profile_path):
        # Fallback check metadata
        meta = get_dataset_metadata(dataset_id)
        if not meta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset '{dataset_id}' not found.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for dataset '{dataset_id}' has not been generated or is missing.",
        )

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
        return profile_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read profile data: {str(e)}",
        )


@router.post("/datasets/{dataset_id}/report", response_class=JSONResponse)
async def generate_dataset_report(dataset_id: str):
    """Loads profile for dataset_id, runs LangGraph report pipeline, saves report JSON, and returns it."""
    _ensure_storage_dirs()

    # Load profile JSON
    profile_path = os.path.join(STORAGE_DIR, "profiles", f"{dataset_id}.json")
    if not os.path.exists(profile_path):
        meta = get_dataset_metadata(dataset_id)
        if not meta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset '{dataset_id}' not found.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for dataset '{dataset_id}' is missing. Cannot generate report.",
        )

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load profile for dataset '{dataset_id}': {str(e)}",
        )

    meta = get_dataset_metadata(dataset_id) or {}
    filename = meta.get("filename", f"dataset_{dataset_id}")

    # Generate report via LangGraph pipeline
    try:
        report_data = generate_report(profile_data, filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation pipeline failed: {str(e)}",
        )

    # Save report JSON
    report_path = os.path.join(STORAGE_DIR, "reports", f"{dataset_id}.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save generated report: {str(e)}",
        )

    # Update dataset status in metadata
    meta["status"] = "report_generated"
    save_dataset_metadata(dataset_id, meta)

    return report_data


@router.get("/datasets/{dataset_id}/report", response_class=JSONResponse)
async def get_dataset_report(dataset_id: str):
    """Returns the saved report JSON for a dataset_id if it exists, else raises 404."""
    report_path = os.path.join(STORAGE_DIR, "reports", f"{dataset_id}.json")
    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for dataset '{dataset_id}' has not been generated or does not exist.",
        )

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)
        return report_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read report file: {str(e)}",
        )


@router.post("/datasets/{dataset_id}/query", response_class=JSONResponse)
async def query_dataset_endpoint(dataset_id: str, payload: QueryRequest):
    """Executes a natural language query over a dataset, returning answer text, data, and suggested chart config, and appending to chat history."""
    _ensure_storage_dirs()
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question string cannot be empty.",
        )

    # Verify dataset metadata exists
    meta = get_dataset_metadata(dataset_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found.",
        )

    result = answer_query(question, dataset_id)

    # Append Q&A record to storage/chat_history/{dataset_id}.json
    history_path = os.path.join(STORAGE_DIR, "chat_history", f"{dataset_id}.json")
    history: List[dict] = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    qa_record = {
        "question": question,
        "answer_text": result.get("answer_text", ""),
        "data": result.get("data"),
        "chart_config": result.get("chart_config"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    history.append(qa_record)

    try:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"[datasets.py] Warning: Failed to save chat history: {e}")

    return result


@router.get("/datasets/{dataset_id}/chat-history", response_class=JSONResponse)
async def get_dataset_chat_history(dataset_id: str):
    """Returns stored chat history Q&A records for a dataset."""
    history_path = os.path.join(STORAGE_DIR, "chat_history", f"{dataset_id}.json")
    if not os.path.exists(history_path):
        return []

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load chat history: {str(e)}",
        )


@router.get("/datasets/{dataset_id}/rows", response_class=JSONResponse)
async def get_dataset_rows(dataset_id: str, indices: Optional[str] = None):
    """Loads cached parsed DataFrame and returns rows matching the requested comma-separated list of indices."""
    pickle_path = os.path.join(STORAGE_DIR, "parsed", f"{dataset_id}.pkl")
    if not os.path.exists(pickle_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' parsed file not found.",
        )

    try:
        df = pd.read_pickle(pickle_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load dataset pickle: {str(e)}",
        )

    if not indices:
        sliced_df = df.head(200)
    else:
        try:
            parsed_indices = [int(idx.strip()) for idx in indices.split(",") if idx.strip().isdigit()]
            valid_indices = [idx for idx in parsed_indices if idx in df.index]
            sliced_df = df.loc[valid_indices] if valid_indices else pd.DataFrame()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid indices parameter format: {str(e)}",
            )

    records = json.loads(sliced_df.to_json(orient="records", date_format="iso"))
    return {"rows": records}




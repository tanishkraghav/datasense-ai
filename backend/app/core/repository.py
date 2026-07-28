import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")
METADATA_FILE = os.path.join(STORAGE_DIR, "metadata.json")


def _ensure_storage_dirs():
    """Ensure all required storage directories exist."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(os.path.join(STORAGE_DIR, "datasets"), exist_ok=True)
    os.makedirs(os.path.join(STORAGE_DIR, "parsed"), exist_ok=True)
    os.makedirs(os.path.join(STORAGE_DIR, "profiles"), exist_ok=True)
    os.makedirs(os.path.join(STORAGE_DIR, "reports"), exist_ok=True)
    os.makedirs(os.path.join(STORAGE_DIR, "chat_history"), exist_ok=True)


    if not os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


def save_dataset_metadata(dataset_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Saves metadata for a dataset in the metadata.json repository."""
    _ensure_storage_dirs()

    # Ensure created_at timestamp if missing
    if "created_at" not in metadata:
        metadata["created_at"] = datetime.now(timezone.utc).isoformat()

    all_meta = list_all_metadata_dict()
    all_meta[dataset_id] = metadata

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_meta, f, indent=2)

    return metadata


def get_dataset_metadata(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves metadata for a specific dataset by ID."""
    all_meta = list_all_metadata_dict()
    return all_meta.get(dataset_id)


def list_all_metadata_dict() -> Dict[str, Dict[str, Any]]:
    """Loads all metadata as a dictionary mapping dataset_id -> metadata."""
    _ensure_storage_dirs()
    if not os.path.exists(METADATA_FILE):
        return {}
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def list_all_metadata() -> List[Dict[str, Any]]:
    """Returns a list of all dataset metadata records, sorted by created_at descending."""
    all_meta = list_all_metadata_dict()
    records = list(all_meta.values())
    records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return records

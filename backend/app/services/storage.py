import re
import uuid
from pathlib import Path

# backend/storage (this file is backend/app/services/storage.py)
STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage"

_HEX_UUID_REGEX = re.compile(r"^[0-9a-f]{32}$")


def new_storage_name() -> str:
    return uuid.uuid4().hex


def path_of(storage_name: str) -> Path:
    if not _HEX_UUID_REGEX.match(storage_name):
        raise ValueError("Invalid storage identifier")
    
    resolved_storage_dir = STORAGE_DIR.resolve()
    path = (STORAGE_DIR / storage_name).resolve()
    
    # Enforce strict path traversal check: path must be strictly inside STORAGE_DIR
    if not path.is_relative_to(resolved_storage_dir) or path == resolved_storage_dir:
        raise ValueError("Path traversal attempt detected")
    
    # Block symlink traversal
    if path.is_symlink():
        raise ValueError("Symlink traversal detected")
        
    return path


def save_bytes(storage_name: str, data: bytes) -> None:
    path = path_of(storage_name)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete(storage_name: str) -> None:
    path = path_of(storage_name)
    if path.exists():
        path.unlink()

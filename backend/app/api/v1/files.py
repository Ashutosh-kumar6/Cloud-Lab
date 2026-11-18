import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.project_file import ProjectFile
from app.models.user import User
from app.schemas.file import FileOut
from app.services import storage

router = APIRouter(prefix="/files", tags=["Files"])

ALLOWED_EXTENSIONS = {".py", ".txt", ".md", ".java", ".c", ".cpp", ".sh", ".json", ".csv"}
MAX_FILE_BYTES = 1_000_000
MAX_FILES_PER_USER = 50

# Disallowed dangerous binary / executable signatures
DANGEROUS_MAGIC_HEADERS = [
    b"MZ",  # DOS / Windows PE executable
    b"\x7fELF",  # Linux ELF binary
    b"\xca\xfe\xba\xbe",  # Java class bytecode / Mach-O fat
    b"\xfe\xed\xfa\xce",  # Mach-O 32-bit
    b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit
    b"\xce\xfa\xed\xfe",  # Mach-O reverse
    b"\xcf\xfa\xed\xfe",  # Mach-O reverse
    b"PK\x03\x04",  # ZIP / JAR archive
    b"7z\xbc\xaf\x27\x1c",  # 7-Zip
    b"Rar!\x1a\x07",  # RAR
    b"\x1f\x8b",  # Gzip
]

DISALLOWED_MIME_SUBSTRINGS = [
    "executable",
    "dosexec",
    "x-msdownload",
    "x-sh",  # unless plain text
    "x-sharedlib",
]

FILENAME_SAFE_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*$")


def _sanitize_filename(raw_name: str | None) -> str:
    if not raw_name:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    # Strip any directory path components
    normalized = raw_name.replace("\\", "/")
    filename = Path(normalized).name.strip()

    if not filename or len(filename) > 100:
        raise HTTPException(status_code=400, detail="Filename must be between 1 and 100 characters")

    # Prevent path traversal patterns and leading dots/dashes
    if ".." in filename or filename.startswith((".", "-")):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    if not FILENAME_SAFE_REGEX.match(filename):
        raise HTTPException(
            status_code=400,
            detail="Filename contains forbidden characters. Only alphanumeric, dashes, dots, and underscores allowed.",
        )

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = " ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"File extension '{suffix}' not allowed. Allowed: {allowed}")

    return filename


def _validate_file_content(filename: str, data: bytes, content_type: str | None) -> None:
    # 1. Check against binary / executable magic byte signatures
    for magic in DANGEROUS_MAGIC_HEADERS:
        if data.startswith(magic):
            raise HTTPException(
                status_code=400,
                detail="Binary or executable file signatures are strictly prohibited",
            )

    # 2. Check MIME type if provided
    if content_type:
        lowered_mime = content_type.lower()
        for disallowed in DISALLOWED_MIME_SUBSTRINGS:
            if disallowed in lowered_mime:
                raise HTTPException(
                    status_code=400,
                    detail=f"MIME type '{content_type}' is not allowed",
                )

    # 3. All allowed files are text / code. Check for null bytes (hallmark of binary files)
    if b"\x00" in data:
        raise HTTPException(
            status_code=400,
            detail="Binary content detected; only plain text and source code files are permitted",
        )

    # 4. Validate UTF-8 decodability
    try:
        decoded_text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File content must be valid UTF-8 text",
        )

    # 5. For JSON files, ensure syntax is valid JSON
    if Path(filename).suffix.lower() == ".json":
        try:
            json.loads(decoded_text)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON content",
            )


def _get_own_file(db: Session, user: User, file_id: int) -> ProjectFile:
    record = db.get(ProjectFile, file_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    return record


CHUNK_SIZE = 64 * 1024  # 64 KB streaming chunk size


@router.post("", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filename = _sanitize_filename(file.filename)

    # Stream in chunks and enforce the 1MB limit while streaming to prevent memory exhaustion
    chunks: list[bytes] = []
    total_bytes = 0

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File is too large (maximum 1 MB)",
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    _validate_file_content(filename, data, file.content_type)

    record = db.scalar(
        select(ProjectFile).where(
            ProjectFile.user_id == current_user.id, ProjectFile.filename == filename
        )
    )
    if record is None:
        count = db.scalar(
            select(func.count()).select_from(ProjectFile).where(
                ProjectFile.user_id == current_user.id
            )
        )
        if count >= MAX_FILES_PER_USER:
            raise HTTPException(status_code=400, detail="File limit reached (50 files)")
        record = ProjectFile(
            user_id=current_user.id,
            filename=filename,
            storage_name=storage.new_storage_name(),
            size_bytes=len(data),
        )
        db.add(record)
    else:
        record.size_bytes = len(data)
        record.updated_at = datetime.utcnow()

    storage.save_bytes(record.storage_name, data)
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=list[FileOut])
def list_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(ProjectFile)
        .where(ProjectFile.user_id == current_user.id)
        .order_by(ProjectFile.filename)
    )
    return db.scalars(query).all()


@router.get("/{file_id}", response_model=FileOut)
def get_file_metadata(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_own_file(db, current_user, file_id)


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = _get_own_file(db, current_user, file_id)
    path = storage.path_of(record.storage_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File content is missing")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=record.filename,
    )


@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = _get_own_file(db, current_user, file_id)
    storage.delete(record.storage_name)
    db.delete(record)
    db.commit()
    return {"deleted": True}

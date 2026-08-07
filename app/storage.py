import uuid
from pathlib import Path

from app.config import settings


def save_upload(file_bytes: bytes, original_filename: str) -> tuple[str, str]:
    """
    Returns (stored_path, unique_id_used_in_name). Local-disk
    implementation. To move to S3/GCS: replace this function's body,
    the rest of the app only depends on getting back a path/URI string
    it can hand to PIL/OpenCV — routes and tasks don't know or care
    where bytes physically live.
    """
    ext = Path(original_filename).suffix.lower() or ".jpg"
    unique_name = f"{uuid.uuid4()}{ext}"
    dest = settings.storage_dir / unique_name
    dest.write_bytes(file_bytes)
    return str(dest), unique_name

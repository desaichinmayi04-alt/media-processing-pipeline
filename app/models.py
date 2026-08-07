import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Enum

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Verdict(str, enum.Enum):
    clean = "clean"
    flagged = "flagged"
    suspicious = "suspicious"


class ImageRecord(Base):
    """
    One row per uploaded image. This is intentionally a single wide-ish
    table rather than normalizing checks into a child table — at this
    scale (one analysis pass per image, checks don't change shape often)
    a JSON column for `checks` is simpler to query and evolve than a
    join, and Postgres/SQLite both index JSON reasonably well if this
    ever needs to scale. Documented as a trade-off in the README.
    """
    __tablename__ = "image_records"

    id = Column(String, primary_key=True, default=_uuid)

    # Upload metadata
    original_filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    # Processing lifecycle
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.pending, nullable=False, index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    failure_reason = Column(String, nullable=True)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Analysis outputs
    perceptual_hash = Column(String, nullable=True, index=True)
    extracted_plate_text = Column(String, nullable=True)
    trust_score = Column(Float, nullable=True)          # 0-100
    verdict = Column(Enum(Verdict), nullable=True)
    checks = Column(JSON, nullable=True)                 # list[dict] — see schemas.CheckResult
    exif_meta = Column(JSON, nullable=True)

    def to_status_dict(self):
        return {
            "id": self.id,
            "status": self.status.value if self.status else None,
            "uploaded_at": self.uploaded_at,
            "processing_started_at": self.processing_started_at,
            "processed_at": self.processed_at,
            "retry_count": self.retry_count,
            "failure_reason": self.failure_reason,
        }

    def to_results_dict(self):
        return {
            "id": self.id,
            "status": self.status.value if self.status else None,
            "original_filename": self.original_filename,
            "trust_score": self.trust_score,
            "verdict": self.verdict.value if self.verdict else None,
            "extracted_plate_text": self.extracted_plate_text,
            "perceptual_hash": self.perceptual_hash,
            "checks": self.checks,
            "exif_meta": self.exif_meta,
            "processed_at": self.processed_at,
        }

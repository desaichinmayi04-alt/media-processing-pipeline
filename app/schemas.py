from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class UploadResponse(BaseModel):
    id: str
    status: str
    status_url: str
    results_url: str


class StatusResponse(BaseModel):
    id: str
    status: str
    uploaded_at: datetime
    processing_started_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    retry_count: int
    failure_reason: Optional[str] = None


class CheckResult(BaseModel):
    """
    Every analyzer returns this shape. `passed` is a hard boolean for
    quick filtering; `confidence` (0-1) expresses how sure the check is
    about that verdict, because most of these heuristics are genuinely
    uncertain (e.g. brightness on a shaded auto vs. a real low-light
    shot) and collapsing that to a bare bool would misrepresent it.
    """
    name: str
    passed: bool
    confidence: float
    message: str
    details: dict[str, Any] = {}


class ResultsResponse(BaseModel):
    id: str
    status: str
    original_filename: str
    trust_score: Optional[float] = None
    verdict: Optional[str] = None
    extracted_plate_text: Optional[str] = None
    perceptual_hash: Optional[str] = None
    checks: Optional[list[CheckResult]] = None
    exif_meta: Optional[dict[str, Any]] = None
    processed_at: Optional[datetime] = None

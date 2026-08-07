import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import ImageRecord, ProcessingStatus
from app.schemas import UploadResponse, StatusResponse, ResultsResponse
from app.storage import save_upload
from app.tasks import process_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Intelligent Media Processing Pipeline",
    description="Async image upload + quality/fraud analysis pipeline for field vehicle photos.",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/images", response_model=UploadResponse, status_code=202)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if file.content_type not in settings.allowed_content_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type '{file.content_type}'. Allowed: {settings.allowed_content_types}",
        )

    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Max is {settings.max_upload_mb}MB.",
        )
    if size_mb == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    stored_path, _ = save_upload(file_bytes, file.filename or "upload.jpg")

    record = ImageRecord(
        original_filename=file.filename or "upload.jpg",
        stored_path=stored_path,
        content_type=file.content_type,
        file_size_bytes=len(file_bytes),
        status=ProcessingStatus.pending,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Enqueue async processing. The API returns immediately — the
    # caller polls /status or /results.
    process_image.delay(record.id)

    return UploadResponse(
        id=record.id,
        status=record.status.value,
        status_url=f"/api/v1/images/{record.id}/status",
        results_url=f"/api/v1/images/{record.id}/results",
    )


@app.get("/api/v1/images/{image_id}/status", response_model=StatusResponse)
def get_status(image_id: str, db: Session = Depends(get_db)):
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return record.to_status_dict()


@app.get("/api/v1/images/{image_id}/results", response_model=ResultsResponse)
def get_results(image_id: str, db: Session = Depends(get_db)):
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Image not found")

    if record.status != ProcessingStatus.completed:
        return JSONResponse(
            status_code=409,
            content={
                "id": record.id,
                "status": record.status.value,
                "message": (
                    "Processing not complete yet." if record.status != ProcessingStatus.failed
                    else f"Processing failed: {record.failure_reason}"
                ),
            },
        )
    return record.to_results_dict()


@app.get("/api/v1/images")
def list_images(db: Session = Depends(get_db), limit: int = 20):
    records = db.query(ImageRecord).order_by(ImageRecord.uploaded_at.desc()).limit(limit).all()
    return [r.to_status_dict() for r in records]

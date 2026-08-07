import logging
from datetime import datetime, timezone

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import ImageRecord, ProcessingStatus, Verdict
from app.analyzers.blur import check_blur
from app.analyzers.brightness import check_brightness
from app.analyzers.duplicate import compute_phash, check_duplicate
from app.analyzers.ocr_plate import check_ocr_and_plate
from app.analyzers.screenshot import check_screenshot
from app.analyzers.photo_of_photo import check_photo_of_photo
from app.analyzers.metadata import extract_exif, check_metadata
from app.analyzers.tampering import check_tampering
from app.analyzers.scoring import aggregate

logger = logging.getLogger(__name__)


class UnprocessableImageError(Exception):
    """Permanent failure — retrying will not help (corrupt/unreadable file)."""


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,   # seconds; doubled below for a simple backoff
    acks_late=True,
)
def process_image(self, image_id: str):
    db = SessionLocal()
    try:
        record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
        if record is None:
            logger.error("process_image: no record found for id=%s", image_id)
            return

        record.status = ProcessingStatus.processing
        record.processing_started_at = datetime.now(timezone.utc)
        db.commit()

        # --- Load image (permanent failure if this doesn't work) ---
        try:
            pil_image = Image.open(record.stored_path)
            pil_image.load()  # force decode now, not lazily later
        except (UnidentifiedImageError, OSError) as exc:
            raise UnprocessableImageError(f"Could not decode image file: {exc}") from exc

        cv_image = cv2.imread(record.stored_path)
        if cv_image is None:
            raise UnprocessableImageError("OpenCV could not read the image (unsupported format or corrupt file)")
        gray_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

        # --- Run checks. Each is isolated: one analyzer raising should
        # not take down the whole pipeline, it should show up as a
        # failed/low-confidence check instead. ---
        checks: list[dict] = []

        def run_safely(name, fn, *args):
            try:
                checks.append(fn(*args))
            except Exception as exc:  # noqa: BLE001 - intentionally broad, isolating analyzer failures
                logger.exception("Analyzer %s failed on image %s", name, image_id)
                checks.append({
                    "name": name,
                    "passed": False,
                    "confidence": 0.3,
                    "message": f"Analyzer error: {exc}",
                    "details": {"error": str(exc)},
                })

        exif_dict = extract_exif(pil_image)
        phash = compute_phash(pil_image)

        run_safely("blur_detection", check_blur, gray_image)
        run_safely("brightness_analysis", check_brightness, gray_image)
        run_safely("duplicate_detection", check_duplicate, db, phash, record.id)
        run_safely("ocr_plate_validation", check_ocr_and_plate, pil_image)
        run_safely("screenshot_detection", check_screenshot, pil_image, exif_dict)
        run_safely("photo_of_photo_heuristic", check_photo_of_photo, gray_image)
        run_safely("metadata_analysis", check_metadata, exif_dict)
        run_safely("tampering_heuristic_ela", check_tampering, pil_image)

        trust_score, verdict = aggregate(checks)

        plate_check = next((c for c in checks if c["name"] == "ocr_plate_validation"), None)
        extracted_plate = (plate_check or {}).get("details", {}).get("extracted_plate")

        record.checks = checks
        record.exif_meta = exif_dict
        record.perceptual_hash = phash
        record.extracted_plate_text = extracted_plate
        record.trust_score = trust_score
        record.verdict = Verdict(verdict)
        record.status = ProcessingStatus.completed
        record.processed_at = datetime.now(timezone.utc)
        db.commit()

    except UnprocessableImageError as exc:
        logger.warning("Permanent failure for image %s: %s", image_id, exc)
        _mark_failed(db, image_id, str(exc))

    except Exception as exc:  # noqa: BLE001 - transient failure path, eligible for retry
        db.rollback()
        logger.exception("Transient failure processing image %s (attempt %s)", image_id, self.request.retries)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries))
        _mark_failed(db, image_id, f"Failed after {self.max_retries} retries: {exc}")

    finally:
        db.close()


def _mark_failed(db, image_id: str, reason: str):
    db.rollback()
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if record:
        record.status = ProcessingStatus.failed
        record.failure_reason = reason[:1000]
        record.processed_at = datetime.now(timezone.utc)
        db.commit()

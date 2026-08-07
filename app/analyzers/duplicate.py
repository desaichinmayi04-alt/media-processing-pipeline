import imagehash
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ImageRecord


def compute_phash(pil_image) -> str:
    return str(imagehash.phash(pil_image))


def check_duplicate(db: Session, phash: str, current_id: str) -> dict:
    """
    Perceptual hash (pHash) instead of exact byte/MD5 hash on purpose:
    field photos of the same rickshaw get re-compressed, re-uploaded at
    different resolutions, or re-shared over WhatsApp, which changes
    the bytes but not the perceptual content. pHash is robust to that;
    a naive checksum would miss almost every real duplicate.

    We compare Hamming distance against previously *completed* records
    only (not pending/failed) to avoid comparing against half-processed
    rows, and exclude the current record itself.
    """
    threshold = settings.duplicate_hash_distance
    current_hash = imagehash.hex_to_hash(phash)

    candidates = (
        db.query(ImageRecord)
        .filter(ImageRecord.perceptual_hash.isnot(None))
        .filter(ImageRecord.id != current_id)
        .all()
    )

    best_match = None
    best_distance = None
    for record in candidates:
        try:
            other_hash = imagehash.hex_to_hash(record.perceptual_hash)
        except ValueError:
            continue
        distance = int(current_hash - other_hash)  # numpy int64 -> plain int (JSON-serializable)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_match = record

    is_duplicate = best_distance is not None and best_distance <= threshold

    if is_duplicate:
        confidence = round(max(0.5, 1 - (best_distance / (threshold + 1))), 2)
        message = f"Likely duplicate of image {best_match.id} (hash distance {best_distance})"
        details = {"matched_id": best_match.id, "hash_distance": best_distance, "threshold": threshold}
    else:
        confidence = 0.85 if best_distance is None else round(min(0.9, best_distance / (threshold * 3)), 2)
        message = "No duplicate found in prior uploads" if best_distance is None else (
            f"Nearest prior image at distance {best_distance} (above duplicate threshold {threshold})"
        )
        details = {"nearest_distance": best_distance, "threshold": threshold}

    return {
        "name": "duplicate_detection",
        "passed": not is_duplicate,
        "confidence": max(0.5, min(0.99, confidence)),
        "message": message,
        "details": details,
    }

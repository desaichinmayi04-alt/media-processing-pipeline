import re
import pytesseract

# Standard Indian plate: 2 letters (state) + 1-2 digits (RTO code) +
# 1-3 letters (series) + 4 digits. Also matches the newer BH series:
# YY BH #### XX. Both anchored loosely since OCR spacing is unreliable.
PLATE_PATTERN = re.compile(
    r"\b([A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4})\b"
)
BH_SERIES_PATTERN = re.compile(
    r"\b([0-9]{2}BH[0-9]{4}[A-Z]{1,2})\b"
)


def _normalize(raw_text: str) -> str:
    # Collapse whitespace/newlines and strip characters OCR commonly
    # confuses (pipes, dots) before pattern matching. Keep a
    # space-stripped variant too since real plates are sometimes
    # printed/read with a gap between the RTO code and series.
    cleaned = re.sub(r"[^A-Za-z0-9\s]", "", raw_text).upper()
    return re.sub(r"\s+", "", cleaned)


def check_ocr_and_plate(pil_image) -> dict:
    """
    Runs OCR over the whole frame (field photos aren't cropped to the
    plate) and searches the extracted text for a substring matching
    the Indian plate format. This is intentionally permissive about
    *where* on the image the plate is, and strict about the *format*
    once found — matching the assignment's ask to validate plate
    format specifically, not just "OCR found some text".
    """
    try:
        raw_text = pytesseract.image_to_string(pil_image)
    except Exception as exc:  # pytesseract/binary missing, corrupt image, etc.
        return {
            "name": "ocr_plate_validation",
            "passed": False,
            "confidence": 0.5,
            "message": f"OCR failed to run: {exc}",
            "details": {"error": str(exc)},
        }

    normalized = _normalize(raw_text)
    match = PLATE_PATTERN.search(normalized) or BH_SERIES_PATTERN.search(normalized)

    if match:
        return {
            "name": "ocr_plate_validation",
            "passed": True,
            "confidence": 0.85,
            "message": f"Valid-format plate text detected: {match.group(1)}",
            "details": {"extracted_plate": match.group(1), "raw_ocr_length": len(raw_text)},
        }

    has_any_text = len(raw_text.strip()) > 3
    return {
        "name": "ocr_plate_validation",
        "passed": False,
        "confidence": 0.6 if has_any_text else 0.4,
        "message": (
            "OCR found text but no substring matched a valid Indian plate format"
            if has_any_text
            else "OCR found little to no readable text in the image"
        ),
        "details": {"raw_ocr_length": len(raw_text)},
    }

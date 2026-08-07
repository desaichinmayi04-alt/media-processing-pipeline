import io
import numpy as np
from PIL import Image, ImageChops


def check_tampering(pil_image) -> dict:
    """
    Error Level Analysis (ELA): re-save the image at a fixed JPEG
    quality and diff against the original. Untouched regions of a
    JPEG re-compress to a fairly uniform error level; a region that
    was pasted in or heavily edited after the last save was
    compressed a different number of times and stands out with a
    distinctly different (often higher) error level.

    Caveat documented in README: ELA is well-established for JPEGs but
    much weaker evidence on images that started as PNG (no prior lossy
    compression to diff against), which is common for phone camera
    exports and screenshots. We still run it and report it, but weight
    it low in the aggregate score for non-JPEG sources.
    """
    was_jpeg = pil_image.format == "JPEG"

    rgb_image = pil_image.convert("RGB")
    buffer = io.BytesIO()
    rgb_image.save(buffer, "JPEG", quality=90)
    buffer.seek(0)
    resaved = Image.open(buffer)

    diff = ImageChops.difference(rgb_image, resaved)
    diff_array = np.array(diff).astype(np.float32)

    mean_error = float(diff_array.mean())
    max_error = float(diff_array.max())
    # High local max relative to a low global mean suggests a small,
    # localized edited region rather than uniform re-compression noise.
    spike_ratio = max_error / (mean_error + 1e-6)

    THRESHOLD = 25.0
    is_suspicious = was_jpeg and spike_ratio > THRESHOLD

    confidence = 0.5 if not was_jpeg else (0.65 if is_suspicious else 0.6)

    message = (
        "Non-JPEG source (no meaningful ELA signal available)"
        if not was_jpeg
        else (
            f"Localized error-level spike detected (ratio {spike_ratio:.1f}) — possible edited region"
            if is_suspicious
            else f"Error levels look uniform (ratio {spike_ratio:.1f}), no strong tampering signal"
        )
    )

    return {
        "name": "tampering_heuristic_ela",
        "passed": not is_suspicious,
        "confidence": confidence,
        "message": message,
        "details": {
            "source_was_jpeg": was_jpeg,
            "mean_error": round(mean_error, 2),
            "max_error": round(max_error, 2),
            "spike_ratio": round(spike_ratio, 2),
        },
    }

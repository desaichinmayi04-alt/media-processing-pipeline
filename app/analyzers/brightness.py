import numpy as np
from app.config import settings


def check_brightness(gray_image) -> dict:
    """
    Mean pixel intensity over the grayscale image. Flags both
    under-exposed (dark/low-light) and over-exposed (blown-out/glare)
    shots — both are real field-photo failure modes, not just "too dark".
    """
    mean_intensity = float(np.mean(gray_image))
    dark_t = settings.dark_brightness_threshold
    bright_t = settings.bright_overexposed_threshold

    if mean_intensity < dark_t:
        passed = False
        message = f"Image is under-exposed / low light (mean intensity {mean_intensity:.1f})"
        confidence = round(min(0.95, (dark_t - mean_intensity) / dark_t + 0.5), 2)
    elif mean_intensity > bright_t:
        passed = False
        message = f"Image is over-exposed / washed out (mean intensity {mean_intensity:.1f})"
        confidence = round(min(0.95, (mean_intensity - bright_t) / (255 - bright_t) + 0.5), 2)
    else:
        passed = True
        message = f"Brightness within acceptable range (mean intensity {mean_intensity:.1f})"
        # Confidence highest at the midpoint of the acceptable band
        midpoint = (dark_t + bright_t) / 2
        confidence = round(1 - abs(mean_intensity - midpoint) / midpoint * 0.3, 2)

    return {
        "name": "brightness_analysis",
        "passed": passed,
        "confidence": max(0.5, min(0.99, confidence)),
        "message": message,
        "details": {
            "mean_intensity": round(mean_intensity, 2),
            "dark_threshold": dark_t,
            "bright_threshold": bright_t,
        },
    }

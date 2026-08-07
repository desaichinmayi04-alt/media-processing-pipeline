import cv2
from app.config import settings


def check_blur(gray_image) -> dict:
    """
    Variance of the Laplacian is a standard, cheap proxy for image
    sharpness: a blurry image has fewer sharp edges, so the second
    derivative (Laplacian) has low variance. It's not perfect — a
    photo of a flat wall will score "blurry" even in perfect focus —
    which is exactly why this returns a confidence, not a verdict.
    """
    laplacian_var = cv2.Laplacian(gray_image, cv2.CV_64F).var()
    threshold = settings.blur_laplacian_threshold

    is_blurry = laplacian_var < threshold
    # Confidence scales with distance from the threshold, clamped to [0.5, 0.99]
    ratio = abs(laplacian_var - threshold) / threshold
    confidence = min(0.99, max(0.5, ratio))

    return {
        "name": "blur_detection",
        "passed": not is_blurry,
        "confidence": round(confidence, 2),
        "message": (
            f"Image appears blurry (sharpness score {laplacian_var:.1f}, "
            f"below threshold {threshold:.0f})"
            if is_blurry
            else f"Image sharpness acceptable (score {laplacian_var:.1f})"
        ),
        "details": {"laplacian_variance": round(laplacian_var, 2), "threshold": threshold},
    }

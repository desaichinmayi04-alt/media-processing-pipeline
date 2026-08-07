import numpy as np
import cv2


def check_photo_of_photo(gray_image) -> dict:
    """
    Photographing a screen or a printed photo (rather than the real
    subject) tends to introduce moire interference or repeating grid
    patterns from the display's pixel/subpixel structure. These show
    up as unusually concentrated energy in the mid-to-high frequency
    band of the image's 2D Fourier spectrum, which a normal outdoor
    photo of a rickshaw does not have (its frequency energy is spread
    more smoothly across bands, dominated by low frequencies).

    This is a coarse heuristic, not a moire detector proper — it will
    have false positives on genuinely high-detail textures (e.g. dense
    foliage). Treated as low-to-moderate confidence for that reason.
    """
    f = np.fft.fft2(gray_image)
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift)

    h, w = gray_image.shape
    cy, cx = h // 2, w // 2

    # Ring masks: low freq = near center, mid/high freq = further out
    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    max_dist = np.sqrt(cy ** 2 + cx ** 2)

    low_mask = dist < 0.15 * max_dist
    mid_high_mask = dist >= 0.15 * max_dist

    low_energy = magnitude[low_mask].sum()
    mid_high_energy = magnitude[mid_high_mask].sum()
    total_energy = low_energy + mid_high_energy + 1e-9

    mid_high_ratio = mid_high_energy / total_energy

    # Threshold picked empirically as a starting point — documented in
    # README as something to calibrate against a labeled dataset.
    THRESHOLD = 0.55
    is_suspicious = mid_high_ratio > THRESHOLD

    confidence = 0.55 if is_suspicious else 0.6

    return {
        "name": "photo_of_photo_heuristic",
        "passed": not is_suspicious,
        "confidence": confidence,
        "message": (
            f"Elevated high-frequency energy ratio ({mid_high_ratio:.2f}) — "
            "possible re-photographed screen/print"
            if is_suspicious
            else f"Frequency profile looks like a direct photograph ({mid_high_ratio:.2f})"
        ),
        "details": {"mid_high_frequency_ratio": round(float(mid_high_ratio), 3), "threshold": THRESHOLD},
    }

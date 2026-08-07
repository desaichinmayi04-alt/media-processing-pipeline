"""
Unit tests for individual analyzers. These use synthetic images
(generated in-memory) rather than the sample images, so they run
deterministically and fast, independent of any specific photo.
"""
import numpy as np
import cv2
from PIL import Image

from app.analyzers.blur import check_blur
from app.analyzers.brightness import check_brightness
from app.analyzers.ocr_plate import check_ocr_and_plate, _normalize, PLATE_PATTERN
from app.analyzers.scoring import aggregate


def _solid_gray_array(value: int, size=(200, 200)):
    return np.full(size, value, dtype=np.uint8)


def _sharp_checkerboard(size=(200, 200)):
    arr = np.zeros(size, dtype=np.uint8)
    arr[::2, ::2] = 255
    arr[1::2, 1::2] = 255
    return arr


def test_blur_detection_flags_flat_image_as_blurry():
    flat = _solid_gray_array(128)
    result = check_blur(flat)
    assert result["passed"] is False
    assert result["name"] == "blur_detection"


def test_blur_detection_passes_high_frequency_image():
    sharp = _sharp_checkerboard()
    result = check_blur(sharp)
    assert result["passed"] is True


def test_brightness_flags_dark_image():
    dark = _solid_gray_array(10)
    result = check_brightness(dark)
    assert result["passed"] is False
    assert "under-exposed" in result["message"] or "low light" in result["message"]


def test_brightness_flags_overexposed_image():
    bright = _solid_gray_array(250)
    result = check_brightness(bright)
    assert result["passed"] is False
    assert "over-exposed" in result["message"] or "washed out" in result["message"]


def test_brightness_passes_midrange_image():
    mid = _solid_gray_array(120)
    result = check_brightness(mid)
    assert result["passed"] is True


def test_plate_pattern_matches_standard_format():
    assert PLATE_PATTERN.search(_normalize("MH12AB1234"))
    assert PLATE_PATTERN.search(_normalize("KA 05 MJ 3232"))


def test_plate_pattern_rejects_garbage_text():
    assert PLATE_PATTERN.search(_normalize("HELLO WORLD")) is None


def test_scoring_aggregate_all_pass_gives_high_score():
    checks = [
        {"name": "blur_detection", "passed": True, "confidence": 0.9},
        {"name": "brightness_analysis", "passed": True, "confidence": 0.9},
        {"name": "duplicate_detection", "passed": True, "confidence": 0.9},
        {"name": "ocr_plate_validation", "passed": True, "confidence": 0.9},
    ]
    score, verdict = aggregate(checks)
    assert score > 80
    assert verdict == "clean"


def test_scoring_aggregate_high_confidence_duplicate_is_suspicious():
    checks = [
        {"name": "blur_detection", "passed": True, "confidence": 0.9},
        {"name": "duplicate_detection", "passed": False, "confidence": 0.95},
    ]
    score, verdict = aggregate(checks)
    assert verdict == "suspicious"


def test_scoring_aggregate_low_confidence_fail_only_flagged_not_suspicious():
    checks = [
        {"name": "blur_detection", "passed": True, "confidence": 0.9},
        {"name": "photo_of_photo_heuristic", "passed": False, "confidence": 0.5},
    ]
    score, verdict = aggregate(checks)
    assert verdict in ("flagged", "clean")
    assert verdict != "suspicious"

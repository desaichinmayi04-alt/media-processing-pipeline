from PIL.ExifTags import TAGS

# Common device screen resolutions (width, height) — screenshots are
# pixel-perfect copies of the screen buffer, so their dimensions land
# exactly on one of these far more often than a camera photo would.
KNOWN_SCREEN_RESOLUTIONS = {
    (1080, 1920), (1080, 2340), (1080, 2400), (828, 1792), (1170, 2532),
    (1179, 2556), (1284, 2778), (1440, 3200), (720, 1600), (1440, 2960),
    (2532, 1170), (2778, 1284), (1920, 1080),
}


def check_screenshot(pil_image, exif_dict: dict) -> dict:
    """
    Two independent signals, combined additively rather than as a
    single rule, because either one alone is weak:
      1. No camera-identifying EXIF (Make/Model) — screenshots never
         have this, but plenty of legitimately re-compressed camera
         photos strip EXIF too, so this alone is NOT conclusive.
      2. Dimensions exactly match a known device screen resolution.
    Both present -> high confidence screenshot. Only one -> flagged
    but low confidence, left for a human/downstream reviewer.
    """
    width, height = pil_image.size
    has_camera_exif = any(k in exif_dict for k in ("Make", "Model"))
    dims_match_screen = (width, height) in KNOWN_SCREEN_RESOLUTIONS

    signals = int(not has_camera_exif) + int(dims_match_screen)

    if signals == 2:
        passed, confidence = False, 0.8
        message = f"Likely a screenshot: no camera EXIF and dimensions ({width}x{height}) match a known device screen"
    elif signals == 1:
        passed, confidence = False, 0.45
        reason = "no camera EXIF present" if not has_camera_exif else f"dimensions ({width}x{height}) match a known screen size"
        message = f"Possible screenshot ({reason}), but not conclusive"
    else:
        passed, confidence = True, 0.7
        message = "No screenshot indicators found"

    return {
        "name": "screenshot_detection",
        "passed": passed,
        "confidence": confidence,
        "message": message,
        "details": {
            "has_camera_exif": has_camera_exif,
            "dimensions": [width, height],
            "dims_match_known_screen": dims_match_screen,
        },
    }

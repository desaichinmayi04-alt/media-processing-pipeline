from PIL.ExifTags import TAGS

# Software tag values that indicate the image passed through an editor
# after capture. Not proof of malicious tampering — legitimate cropping
# happens — but worth surfacing for a human reviewer.
KNOWN_EDITORS = ("photoshop", "gimp", "snapseed", "lightroom", "picsart", "canva")


def extract_exif(pil_image) -> dict:
    exif_raw = pil_image.getexif()
    if not exif_raw:
        return {}
    result = {}
    for tag_id, value in exif_raw.items():
        tag_name = TAGS.get(tag_id, tag_id)
        try:
            # Keep only JSON-serializable, human-relevant values
            if isinstance(value, (bytes,)):
                continue
            result[str(tag_name)] = value if isinstance(value, (str, int, float)) else str(value)
        except Exception:
            continue
    return result


def check_metadata(exif_dict: dict) -> dict:
    """
    Flags two things: total absence of capture metadata (common when
    an image has been re-saved/re-shared, which is itself a mild
    signal worth surfacing even if not disqualifying) and an explicit
    editing-software tag (a much stronger signal).
    """
    software = str(exif_dict.get("Software", "")).lower()
    edited_by_known_tool = any(editor in software for editor in KNOWN_EDITORS)
    has_any_exif = len(exif_dict) > 0

    if edited_by_known_tool:
        return {
            "name": "metadata_analysis",
            "passed": False,
            "confidence": 0.75,
            "message": f"EXIF Software tag indicates editing tool: '{exif_dict.get('Software')}'",
            "details": {"software_tag": exif_dict.get("Software"), "has_exif": has_any_exif},
        }

    if not has_any_exif:
        return {
            "name": "metadata_analysis",
            "passed": False,
            "confidence": 0.35,
            "message": "No EXIF metadata present (image may have been re-saved, re-compressed, or stripped)",
            "details": {"has_exif": False},
        }

    return {
        "name": "metadata_analysis",
        "passed": True,
        "confidence": 0.55,
        "message": "EXIF metadata present with no known-editor signature",
        "details": {"has_exif": True, "keys_found": list(exif_dict.keys())[:15]},
    }

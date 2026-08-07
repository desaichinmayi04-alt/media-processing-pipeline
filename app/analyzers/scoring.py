"""
Aggregates individual CheckResult dicts into a single explainable
trust_score (0-100) and a verdict (clean / flagged / suspicious).

Design rationale (see README "System Thinking"):
- Checks are NOT weighted equally. Duplicate detection and plate
  validation are stronger, more direct fraud/quality signals for this
  use case than, say, brightness, so they carry more weight.
- Each check's contribution is also scaled by its own confidence, so
  a low-confidence flag (e.g. the photo-of-photo FFT heuristic) can't
  tank the score as hard as a high-confidence one (e.g. a hard
  duplicate match). This is the concrete implementation of "structuring
  uncertainty" rather than treating every heuristic as equally certain.
- The score is a decision-support number for a human reviewer, not an
  automated accept/reject gate — that's a deliberate scope choice
  given the assignment says accuracy isn't the point.
"""

CHECK_WEIGHTS = {
    "blur_detection": 15,
    "brightness_analysis": 10,
    "duplicate_detection": 25,
    "ocr_plate_validation": 20,
    "screenshot_detection": 15,
    "photo_of_photo_heuristic": 8,
    "metadata_analysis": 5,
    "tampering_heuristic_ela": 2,
}


def aggregate(check_results: list[dict]) -> tuple[float, str]:
    total_weight = 0.0
    earned = 0.0

    for check in check_results:
        weight = CHECK_WEIGHTS.get(check["name"], 5)
        confidence = check.get("confidence", 0.5)
        total_weight += weight

        if check["passed"]:
            earned += weight
        else:
            # Failing check still contributes partial credit inversely
            # proportional to how confident we are it actually failed —
            # a low-confidence fail costs less than a high-confidence one.
            earned += weight * (1 - confidence)

    trust_score = round((earned / total_weight) * 100, 1) if total_weight else 0.0

    failed_checks = [c for c in check_results if not c["passed"]]
    high_confidence_fails = [c for c in failed_checks if c.get("confidence", 0) >= 0.75]

    if trust_score >= 80 and not high_confidence_fails:
        verdict = "clean"
    elif high_confidence_fails or trust_score < 50:
        verdict = "suspicious"
    else:
        verdict = "flagged"

    return trust_score, verdict

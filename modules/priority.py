"""
Priority engine (Stage 5.4).

Computes review priority from measured factors. Handles None values gracefully.
"""
WEIGHTS = {
    "change": 0.45,
    "boundary": 0.20,
    "image_quality": 0.15,
    "registration": 0.20,
}
HISTORY_NUDGE = 0.05


def _change_factor(change_percentage):
    """0..1; 12% visual change or more saturates the factor."""
    if change_percentage is None:
        return None
    return min(change_percentage / 12.0, 1.0)


def _boundary_factor(iou):
    """0..1; an IoU (recorded vs candidate boundary) below 0.5 saturates.

    IoU 1.0 (identical) -> 0; IoU <= 0.5 -> 1. None when no boundary
    comparison exists for this analysis.
    """
    if iou is None:
        return None
    if iou >= 1.0:
        return 0.0
    if iou <= 0.5:
        return 1.0
    return (1.0 - iou) / 0.5


def _image_quality_factor(quality_a, quality_b):
    """0..1 blur/contrast penalty from the WORGER of the two images.

    Uses the Laplacian-variance blur score relative to a soft reference:
    under ~100 the image is very soft. Both values are real measurements.
    """
    scores = [q["blur_score"] for q in (quality_a, quality_b) if q]
    if not scores:
        return None
    weakest = min(scores)
    if weakest >= 400:
        return 0.0
    return min(max((400 - weakest) / 400, 0.0), 1.0)


def _registration_factor(inlier_ratio, median_error):
    """0..1 registration risk; good alignment -> 0, weak -> 1."""
    if inlier_ratio is None:
        return None
    ratio_risk = 1.0 - min(inlier_ratio / 0.7, 1.0)     # 0.7+ inliers -> 0 risk
    error_risk = 0.0
    if median_error is not None:
        error_risk = min(median_error / 8.0, 1.0)       # 8 px -> saturated
    return min(0.6 * ratio_risk + 0.4 * error_risk, 1.0)


def _history_factor(previous_changes):
    """Small nudge from earlier analyses of the same parcel.

    Repeated moderate changes hint at an ongoing process; a quiet
    history slightly lowers the priority of a marginal new result.
    """
    if not previous_changes:
        return 0.0
    recent = previous_changes[:3]
    average = sum(c for c in recent if c is not None) / len(recent)
    if average >= 8.0:
        return HISTORY_NUDGE
    if average <= 1.0:
        return -HISTORY_NUDGE
    return 0.0


def compute_priority(change_percentage, boundary_iou=None,
                     image_quality=None, registration=None,
                     previous_changes=None):
    """Return (priority_label, factor_breakdown_dict).

    Labels: 'low' | 'medium' | 'high' | 'insufficient_data'.
    The breakdown contains every 0..1 factor (None when that input was
    not available) so the UI can show exactly which term did what.
    """
    if change_percentage is None:
        return "insufficient_data", {"reason": "No change measurement available."}

    change = _change_factor(change_percentage)
    boundary = _boundary_factor(boundary_iou)
    quality = _image_quality_factor(**image_quality) if image_quality else None
    reg = _registration_factor(
        registration.get("inlier_ratio"), registration.get("median_reprojection_error")
    ) if registration else None

    # Handle None factors for weighted sum
    available_factors = []
    available_weights = []
    if change is not None:
        available_factors.append(change)
        available_weights.append(WEIGHTS["change"])
    if boundary is not None:
        available_factors.append(boundary)
        available_weights.append(WEIGHTS["boundary"])
    if quality is not None:
        available_factors.append(quality)
        available_weights.append(WEIGHTS["image_quality"])
    if reg is not None:
        available_factors.append(reg)
        available_weights.append(WEIGHTS["registration"])

    # If no valid factors, return insufficient data
    if not available_factors:
        return "insufficient_data", {"reason": "Essential data missing."}

    weight_sum = sum(available_weights)
    score = sum(f * w for f, w in zip(available_factors, available_weights)) / weight_sum
    score += _history_factor(previous_changes or [])
    score = max(0.0, min(score, 1.0))

    if score >= 0.55:
        label = "high"
    elif score >= 0.25:
        label = "medium"
    else:
        label = "low"

    breakdown = {
        "change_factor": None if change is None else round(change, 3),
        "boundary_factor": None if boundary is None else round(boundary, 3),
        "image_quality_factor": None if quality is None else round(quality, 3),
        "registration_factor": round(reg, 3) if reg is not None else None,
        "history_nudge": round(_history_factor(previous_changes or []), 3),
        "score": round(score, 3),
        "weights": WEIGHTS,
    }
    return label, breakdown

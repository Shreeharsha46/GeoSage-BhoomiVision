"""
GeoSage - Explainability (Stage 5.3).

Answers "WHY WAS THIS AREA FLAGGED?" for each detected region using ONLY
values that the pipeline actually measured. Nothing is invented: if a
geographic area cannot be computed (no scale information), the text says
so explicitly.

Every explanation carries the relevant limitations and the required
manual-verification advice, as mandated by the project specification.
"""

REGISTERED_HINTS = {
    "feature_detection": "feature alignment failed (too little texture)",
    "matching": "feature matching was unreliable",
    "ransac": "match geometry was inconsistent",
    "sanity_check": "the estimated transform was implausible",
    "reprojection": "alignment error was too high",
}


def geographic_area_text(region, metres_per_pixel):
    """Human text for the region's size; honest about what is unknown."""
    if metres_per_pixel:
        area_m2 = region["pixel_area"] * metres_per_pixel * metres_per_pixel
        if area_m2 >= 10_000:
            return f"approx. {area_m2 / 10_000:.2f} ha"
        return f"approx. {area_m2:.0f} m²"
    return (f"{region['pixel_area']} px (geographic size unavailable - the "
            "images carry no scale metadata, so pixel area is all that can "
            "be reported)")


def explain_region(region, region_index, change_percentage, registration_stats,
                   metres_per_pixel=None):
    """Build the explanation dict for one detected region.

    All numbers come from `region` and `registration_stats`, i.e. from
    real algorithm output. The 'reason' describes the measured evidence;
    'limitations' states what this classical method cannot determine.
    """
    priority = region.get("priority") or "unrated"
    intensity = region.get("mean_intensity")
    intensity_text = (f"mean pixel difference {intensity:.0f}/255"
                      if intensity is not None else "intensity not measured")

    area_text = geographic_area_text(region, metres_per_pixel)
    inliers = registration_stats.get("inlier_ratio")
    inlier_text = (f"{inliers * 100:.0f}% feature-inlier agreement"
                   if inliers is not None else "registration quality unknown")

    reason = (
        f"Region {region_index} covers {area_text} with {intensity_text} "
        f"against the registered previous image. The detection method "
        f"({region.get('detection_method', 'difference thresholding')}) flagged "
        f"it because its pixels differ from the previous capture more than "
        f"the scene-wide Otsu threshold. Alignment confidence: {inlier_text}. "
        f"The overall visual change for this pair is {change_percentage:.2f}%."
    )

    limitations = [
        "This is visual pixel change, not a confirmed physical land change.",
        "Seasonal vegetation cycles, shadows and illumination differences can "
        "produce similar pixel differences.",
        "The classifier-free method cannot say WHAT changed (construction vs "
        "vegetation vs water).",
    ]
    if not metres_per_pixel:
        limitations.append(
            "No georeferencing/scale metadata: areas are reported in pixels only."
        )

    return {
        "region_index": region_index,
        "pixel_area": region["pixel_area"],
        "bbox": region.get("bbox"),
        "centroid": region.get("centroid"),
        "mean_intensity": intensity,
        "priority": priority,
        "reason": reason,
        "limitations": limitations,
        "recommended_action": (
            "Verify on the ground or against cadastral records before drawing "
            "any conclusion; submit for human review."
        ),
    }


def explain_registration_failure(failure_reason, failure_stage):
    """Explanation text used when registration failed outright."""
    stage_text = REGISTERED_HINTS.get(failure_stage, failure_stage or "unknown stage")
    return {
        "summary": ("The two images could not be reliably aligned, so no change "
                    "measurement was produced."),
        "reason": failure_reason,
        "detail": f"Registration failed during {stage_text}.",
        "recommended_action": (
            "Upload images of the same area with sufficient texture and overlap; "
            "avoid pairs that are too different in zoom or viewing angle."
        ),
        "limitations": [
            "Without registration, any pixel comparison would be meaningless, "
            "so GeoSage refuses to produce one.",
        ],
    }

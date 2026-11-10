"""
GeoSage - Change detection (Stage 3.3).

Compares two ALREADY-REGISTERED grayscale images and produces:

  difference map -> noise reduction -> Otsu threshold ->
  morphological cleanup -> connected regions -> per-region statistics.

The change percentage is computed strictly inside the valid overlap area:

    change% = changed_valid_pixels / valid_comparison_pixels * 100

Non-overlapping pixels (where one image has no data) never enter the
denominator, so partial-coverage images cannot inflate the score.

The result is a *visual* change report. It is explicitly not evidence of
a physical land change - illumination, shadows, season and compression
artifacts also alter pixels (mitigated, not eliminated, by CLAHE and
morphological filtering).
"""
import cv2
import numpy as np

from modules.preprocessing import normalize_contrast

MIN_REGION_PIXELS = 40        # smaller blobs are noise, not reportable regions
MAX_REGIONS_KEPT = 50         # report the largest N regions only
MAX_REASONABLE_CHANGE_PCT = 95.0

MASK_CHANGED = 255
MASK_VALID = 255


class ChangeDetectionError(Exception):
    """Raised when inputs are unusable (shape mismatch etc.)."""


def compute_difference(old_gray, new_gray):
    """Absolute difference on contrast-normalized grayscale copies.

    Returns the raw difference map (uint8). CLAHE reduces global
    illumination bias first; Gaussian blur then suppresses sensor noise.
    """
    if old_gray.shape != new_gray.shape:
        raise ChangeDetectionError(
            "Registered images must share the same dimensions "
            f"(got {old_gray.shape} vs {new_gray.shape})."
        )
    old_eq = normalize_contrast(old_gray)
    new_eq = normalize_contrast(new_gray)
    diff = cv2.absdiff(old_eq, new_eq)
    diff = cv2.GaussianBlur(diff, (5, 5), 0)
    return diff


def threshold_difference(diff, valid_mask=None):
    """Otsu threshold on the difference map, restricted to valid pixels.

    Otsu picks the separating value from the actual intensity histogram
    of THIS image pair - no hand-tuned magic constant. When almost
    nothing changed, Otsu can cut low; a floor keeps quiet scenes quiet.
    """
    otsu_thr, binary = cv2.threshold(diff, 0, MASK_CHANGED, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    effective_thr = max(int(otsu_thr), 25)  # floor: ignore sub-noise differences
    _, binary = cv2.threshold(diff, effective_thr, MASK_CHANGED, cv2.THRESH_BINARY)
    if valid_mask is not None:
        binary = cv2.bitwise_and(binary, valid_mask)
    return binary.astype(np.uint8), int(effective_thr)


def morphological_cleanup(binary):
    """Open (remove speckles) then close (fill pinholes) the change mask."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=2)
    return closed.astype(np.uint8)


def extract_regions(binary, diff, min_pixels=MIN_REGION_PIXELS):
    """Connected-component analysis -> structured region records.

    Each record carries real measured values only: pixel area, bounding
    box, centroid and mean difference intensity inside the component.
    Sorted by area, largest first, capped at MAX_REGIONS_KEPT.
    """
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    regions = []
    for label in range(1, count):  # 0 is background
        x, y, w, h, area = stats[label]
        if area < min_pixels:
            continue
        component = (labels == label)
        mean_intensity = float(diff[component].mean()) if diff is not None else None
        cx, cy = centroids[label]
        regions.append({
            "pixel_area": int(area),
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "centroid": [round(float(cx), 1), round(float(cy), 1)],
            "mean_intensity": round(mean_intensity, 2) if mean_intensity is not None else None,
        })
    regions.sort(key=lambda r: r["pixel_area"], reverse=True)
    return regions[:MAX_REGIONS_KEPT]


def detect_changes(old_gray, new_gray, overlap_mask):
    """Full visual-change pipeline for a registered image pair.

    Returns a result dict with the change percentage (over VALID pixels
    only), the binary mask, the raw difference map and region records.
    Raises ChangeDetectionError on unusable inputs.
    """
    if old_gray.shape != new_gray.shape:
        raise ChangeDetectionError("Image shapes differ; register before comparing.")

    valid = overlap_mask if overlap_mask is not None else np.full_like(old_gray, MASK_VALID)
    valid_pixels = int(np.count_nonzero(valid))
    if valid_pixels == 0:
        raise ChangeDetectionError(
            "The two images do not overlap - no valid comparison area exists."
        )

    diff = compute_difference(old_gray, new_gray)
    binary, threshold = threshold_difference(diff, valid)
    binary = morphological_cleanup(binary)
    binary = cv2.bitwise_and(binary, valid)  # cleanup may bleed outside the overlap

    changed_pixels = int(np.count_nonzero(binary))
    change_percentage = changed_pixels / valid_pixels * 100.0

    regions = extract_regions(binary, diff)

    return {
        "change_percentage": round(change_percentage, 2),
        "changed_pixels": changed_pixels,
        "valid_pixels": valid_pixels,
        "difference_image": diff,
        "change_mask": binary,
        "threshold_used": threshold,
        "regions": regions,
        "flag_suspicious": change_percentage > MAX_REASONABLE_CHANGE_PCT,
    }

"""
GeoSage - Classical land-use baseline (Stage 5.1).

An explicitly LABELLED heuristic computer-vision baseline. It is NOT a
trained machine-learning model and its scores are NOT calibrated
probabilities. Segmentation uses HSV colour ranges plus simple texture
and edge statistics:

  vegetation   strong green dominance
  agriculture  yellow-green dominance (crops / fields)
  built-up     low saturation + high value + high edge density
  bare soil    orange/brown dominance
  water        blue dominance with low texture
  other        everything else

Each category's share of the valid scene area is returned. Categories
overlap by design of colour perception; proportions are observations,
not predictions. Where a pretrained segmentation model is impractical
(no download, offline requirement), this baseline gives an honest first
screen and is always presented as such.
"""
import cv2
import numpy as np

CATEGORIES = ["vegetation", "agriculture", "builtup", "bare_soil", "water", "other"]

CATEGORY_LABELS = {
    "vegetation": "Vegetation",
    "agriculture": "Agricultural land",
    "builtup": "Built-up areas",
    "bare_soil": "Bare soil",
    "water": "Water bodies",
    "other": "Other / mixed",
}

# HSV ranges (OpenCV hue is 0-179): category -> (lower bound, upper bound)
RANGES = {
    "vegetation": ((35, 40, 40), (85, 255, 255)),
    "agriculture": ((20, 60, 60), (35, 255, 255)),
    "water": ((90, 30, 30), (130, 255, 200)),
    "bare_soil": ((10, 60, 60), (20, 255, 255)),
}

METHOD = "classical HSV segmentation baseline (not a trained model)"


def _edge_density(gray):
    """Share of strong edge pixels - built-up surfaces are edge-rich."""
    edges = cv2.Canny(gray, 60, 150)
    return float(np.count_nonzero(edges)) / edges.size


def classify_landuse(bgr):
    """Compute category proportions for one BGR image.

    Returns {"proportions": {cat: 0..1}, "edge_density": float,
             "method": METHOD, "segmentation_png": bytes or None}.
    """
    height, width = bgr.shape[:2]
    small = cv2.resize(bgr, (width // 2, height // 2), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    total = small.shape[0] * small.shape[1]

    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    counts = {cat: 0 for cat in CATEGORIES}
    for cat, (lo, hi) in RANGES.items():
        mask = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        counts[cat] = int(np.count_nonzero(mask))

    # Built-up: desaturated, bright, edge-dense surfaces.
    edges = cv2.Canny(gray, 60, 150)
    edge_density = float(np.count_nonzero(edges)) / edges.size
    neutral = (sat < 60) & (val > 90)
    neutral_count = int(np.count_nonzero(neutral))

    classified = sum(counts.values())
    if classified < total:
        # Remaining neutral pixels lean built-up when the scene is edge-rich.
        counts["builtup"] += int(neutral_count * (0.65 if edge_density > 0.08 else 0.25))
    counts["builtup"] = min(counts["builtup"], total)

    # Assign leftovers to 'other' so proportions always sum to ~1.
    assigned = sum(min(c, total) for c in counts.values())
    counts["other"] = max(total - assigned, 0)

    proportions = {cat: counts[cat] / total for cat in CATEGORIES}
    return {
        "proportions": {k: round(v, 4) for k, v in proportions.items()},
        "edge_density": round(edge_density, 4),
        "method": METHOD,
        "segmentation_png": _segmentation_png(small, hsv, neutral),
    }


def _segmentation_png(small_bgr, hsv, neutral_mask):
    """Colour-coded segmentation overview image (PNG bytes)."""
    canvas = np.zeros_like(small_bgr)
    canvas[(hsv[:, :, 0] >= 35) & (hsv[:, :, 0] <= 85) & (hsv[:, :, 1] >= 40)] = (40, 160, 40)
    canvas[(hsv[:, :, 0] >= 20) & (hsv[:, :, 0] < 35) & (hsv[:, :, 1] >= 60)] = (40, 140, 220)
    canvas[(hsv[:, :, 0] >= 10) & (hsv[:, :, 0] < 20) & (hsv[:, :, 1] >= 60)] = (60, 110, 190)
    canvas[(hsv[:, :, 0] >= 90) & (hsv[:, :, 0] <= 130) & (hsv[:, :, 1] >= 30)] = (220, 120, 40)
    canvas[neutral_mask] = (170, 170, 170)
    ok, buffer = cv2.imencode(".png", canvas)
    return buffer.tobytes() if ok else None


def compare_landuse(old_result, new_result):
    """Per-category transition table between the two observations."""
    transitions = []
    old_p, new_p = old_result["proportions"], new_result["proportions"]
    for cat in CATEGORIES:
        delta = new_p[cat] - old_p[cat]
        if abs(delta) >= 0.005:  # ignore sub-0.5% jitter
            direction = "increase" if delta > 0 else "decrease"
            transitions.append({
                "category": cat,
                "label": CATEGORY_LABELS[cat],
                "old": old_p[cat],
                "new": new_p[cat],
                "delta": round(delta, 4),
                "direction": direction,
            })
    transitions.sort(key=lambda t: abs(t["delta"]), reverse=True)
    return transitions

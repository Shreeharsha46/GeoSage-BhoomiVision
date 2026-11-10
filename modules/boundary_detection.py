"""
GeoSage - Candidate boundary detection from imagery (Stage 4.2).

Classical edge/contour detection that proposes CANDIDATE boundary-like
polygons in IMAGE pixel space. These are visual image features - field
edges, roads, fence lines, texture breaks. They are explicitly NOT
legal property boundaries, and the UI labels them as candidates.

Pipeline: grayscale -> blur -> Canny edges -> morphological close ->
contour extraction -> polygon approximation (Douglas-Peucker).
"""
import cv2
import numpy as np

from modules.preprocessing import downscale

MIN_CONTOUR_AREA = 400       # px; smaller blobs are texture noise
MAX_POLYGONS = 12            # keep the strongest few for review
MAX_POINTS_PER_POLY = 40     # simplification budget


def detect_candidate_boundaries(bgr, max_width=1200):
    """Return candidate polygons in image pixel coordinates.

    Each polygon: {"points": [[x, y], ...], "area_px": float,
    "closed": True, "space": "image", "note": ...}
    """
    small = downscale(bgr, max_width)
    scale = bgr.shape[1] / small.shape[1]

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Close small gaps so field edges form continuous curves.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scored = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < MIN_CONTOUR_AREA:
            continue
        scored.append((area, contour))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    polygons = []
    for area, contour in scored[:MAX_POLYGONS]:
        epsilon = 0.005 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if approx.shape[0] < 3:
            continue
        if approx.shape[0] > MAX_POINTS_PER_POLY:
            approx = cv2.approxPolyDP(contour, epsilon * 3, True)
        points = [[round(float(p[0][0]) * scale, 1), round(float(p[0][1]) * scale, 1)]
                  for p in approx]
        polygons.append({
            "points": points,
            "area_px": round(area * scale * scale, 1),
            "closed": True,
            "space": "image",
        })
    return polygons


def annotate_candidates(bgr, polygons):
    """Draw candidate polygons on a copy of the image (PNG bytes)."""
    canvas = bgr.copy()
    for i, poly in enumerate(polygons, start=1):
        pts = np.array(poly["points"], dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [pts], True, (255, 180, 40), 2)  # orange
        cx = int(np.mean([p[0] for p in poly["points"]]))
        cy = int(np.mean([p[1] for p in poly["points"]]))
        cv2.putText(canvas, f"C{i}", (cx, cy), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (255, 255, 255), 2, cv2.LINE_AA)
    ok, buffer = cv2.imencode(".png", canvas)
    return buffer.tobytes() if ok else None

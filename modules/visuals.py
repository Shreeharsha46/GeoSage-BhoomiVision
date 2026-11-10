"""
GeoSage - Analysis artifacts and heatmaps (Stages 3.4 & 4.6).

Generates the downloadable/visual outputs for one analysis:

  - difference visualisation (coloured),
  - binary change mask,
  - green -> yellow -> red change-intensity heatmap,
  - contour overlay on the previous image,
  - side-by-side comparison sheet.

Colours encode PIXEL-DIFFERENCE INTENSITY only. They are unrelated to
the review priority of a boundary mismatch, and they do not classify
the type of change.
"""
import cv2
import numpy as np

from modules.change_detection import MASK_CHANGED

# Colour ramp (BGR) for the heatmap: green -> yellow -> red.
GREEN = (0, 200, 0)
YELLOW = (0, 210, 210)
RED = (0, 60, 230)


def _encode_png(image):
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG encoding failed.")
    return buffer.tobytes()


def difference_visual(diff):
    """Difference map as a perceptually coloured image (Jet)."""
    coloured = cv2.applyColorMap(diff, cv2.COLORMAP_JET)
    return _encode_png(coloured)


def change_mask_png(mask):
    """Binary change mask as a clean black/white PNG."""
    return _encode_png(mask)


def heatmap(diff, valid_mask=None, base_image=None, alpha=0.55):
    """Green -> yellow -> red intensity heatmap over the base image.

    - Low intensity  -> green
    - Moderate       -> yellow
    - High intensity -> red

    `base_image` (BGR) is darkened behind the overlay for readability;
    when it is None the heatmap is drawn over a neutral dark ground.
    """
    # Small blur -> smooth, readable intensity fields instead of salt noise.
    smooth = cv2.GaussianBlur(diff.astype(np.float32), (15, 15), 0)
    max_val = float(smooth.max())
    if max_val <= 0:
        norm = smooth
    else:
        norm = smooth / max_val

    height, width = norm.shape[:2]
    overlay = np.zeros((height, width, 3), dtype=np.uint8)

    low = norm < 0.34
    mid = (norm >= 0.34) & (norm < 0.67)
    high = norm >= 0.67

    t_low = norm[low] / 0.34
    overlay[low] = (
        GREEN[0] * (1 - t_low[:, None]) + YELLOW[0] * t_low[:, None]
    )
    t_mid = (norm[mid] - 0.34) / 0.33
    overlay[mid] = (
        YELLOW[0] * (1 - t_mid[:, None]) + RED[0] * t_mid[:, None]
    )
    overlay[high] = RED

    if valid_mask is not None:
        overlay[valid_mask == 0] = 0

    if base_image is None:
        base = np.full((height, width, 3), 30, dtype=np.uint8)
    else:
        base = base_image.copy()
        if base.shape[:2] != (height, width):
            base = cv2.resize(base, (width, height))
        base = cv2.convertScaleAbs(base, alpha=0.45)  # darken for contrast

    blended = cv2.addWeighted(overlay, alpha, base, 1.0 - alpha, 0)
    return _encode_png(blended)


def contour_overlay(base_image, mask):
    """Detected change contours drawn on a copy of the base image."""
    canvas = base_image.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(canvas, contours, -1, (0, 230, 255), 2)  # amber outlines
    return _encode_png(canvas)


def side_by_side(left_image, right_image, label_left="Previous",
                 label_right="Recent (registered)"):
    """Two images stacked horizontally with simple separator (PNG bytes)."""
    height = max(left_image.shape[0], right_image.shape[0])
    width_left = left_image.shape[1]
    width_right = right_image.shape[1]
    canvas = np.zeros((height, width_left + width_right + 4, 3), dtype=np.uint8)
    canvas[:left_image.shape[0], :width_left] = left_image
    canvas[:right_image.shape[0], width_left + 4:] = right_image
    return _encode_png(canvas)


def registered_overlay(base_image, registered_gray):
    """The registered recent image as colour PNG (for reports)."""
    if registered_gray.ndim == 2:
        return _encode_png(cv2.cvtColor(registered_gray, cv2.COLOR_GRAY2BGR))
    return _encode_png(registered_gray)


def region_priority(pixel_area, mean_intensity, valid_pixels):
    """Transparent per-region review priority from real measurements.

    area_share  = region pixels / valid comparison pixels
    intensity   = mean absolute difference inside the region (0-255)

    Both factors are stated openly; the score is a weighted sum with the
    weights documented in the UI. This is a *screening* priority.
    """
    if not valid_pixels:
        return "low"
    area_share = pixel_area / valid_pixels
    intensity_factor = min((mean_intensity or 0) / 100.0, 1.0)
    area_factor = min(area_share / 0.05, 1.0)  # 5% of scene -> saturated
    score = 0.6 * area_factor + 0.4 * intensity_factor
    if score >= 0.55:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"

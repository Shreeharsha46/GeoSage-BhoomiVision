"""
GeoSage - End-to-end analysis pipeline (Stage 3 + Stage 5 integration).

Runs one comparison from stored image paths to persisted-ready result
data. This module owns the PROCESSING; Flask routes own persistence and
responses, keeping the algorithms independent of the web layer.

Steps:
  1. load + validate both images
  2. downscale for analysis speed
  3. quality assessment (feeds explanations and priority)
  4. ORB + RANSAC registration (never forced)
  5. visual change detection over the valid overlap
  6. artifact generation (diff, mask, heatmap, overlay, side-by-side,
     registered view)
  7. land-use baseline observations for both images
  8. region explanations and per-region review priorities
  9. overall review priority via the transparent engine
"""
import time
from pathlib import Path

import cv2
import numpy as np

from modules import visuals
from modules.change_detection import ChangeDetectionError, detect_changes
from modules.explain import explain_region, explain_registration_failure
from modules.landuse import classify_landuse, compare_landuse
from modules.preprocessing import (ImageError, assess_quality, decode_bytes,
                                   downscale, to_grayscale, validate_dimensions)
from modules.priority import compute_priority
from modules.registration import register_images


def _write_artifact(folder, analysis_id, key, png_bytes):
    filename = f"analysis_{analysis_id}_{key}.png"
    path = Path(folder) / filename
    path.write_bytes(png_bytes)
    return path


def run_analysis(old_path, new_path, output_dir, analysis_id,
                 previous_changes=None, boundary_iou=None):
    """Run the complete comparison pipeline.

    `old_path`/`new_path` are absolute paths of the previous and recent
    images; `output_dir` receives the generated artifacts. Returns a
    plain dict - the caller decides persistence.

    `previous_changes`  list of earlier change percentages (history nudge)
    `boundary_iou`      latest recorded-vs-candidate IoU for the parcel
    """
    started = time.time()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    old_bgr = decode_bytes(Path(old_path).read_bytes())
    new_bgr = decode_bytes(Path(new_path).read_bytes())
    validate_dimensions(old_bgr)
    validate_dimensions(new_bgr)

    old_small = downscale(old_bgr, 1600)
    new_small = downscale(new_bgr, 1600)

    old_gray = to_grayscale(old_small)
    new_gray = to_grayscale(new_small)

    quality_old = assess_quality(old_gray)
    quality_new = assess_quality(new_gray)

    registration = register_images(old_gray, new_gray)
    if not registration["success"]:
        return {
            "status": "registration_failed",
            "registration": registration["stats"],
            "explanation": explain_registration_failure(
                registration["reason"], registration["stats"].get("failure_stage")),
            "quality": {"old": quality_old, "new": quality_new},
            "processing_seconds": round(time.time() - started, 2),
            "artifacts": {},
        }

    try:
        change = detect_changes(old_gray, new_gray, registration["overlap_mask"])
    except ChangeDetectionError as exc:
        return {
            "status": "comparison_failed",
            "reason": str(exc),
            "registration": registration["stats"],
            "quality": {"old": quality_old, "new": quality_new},
            "processing_seconds": round(time.time() - started, 2),
            "artifacts": {},
        }

    # --- Artifacts -----------------------------------------------------------
    artifacts = {
        "difference": _write_artifact(output_dir, analysis_id, "difference",
                                      visuals.difference_visual(change["difference_image"])),
        "mask": _write_artifact(output_dir, analysis_id, "mask",
                                visuals.change_mask_png(change["change_mask"])),
        "heatmap": _write_artifact(output_dir, analysis_id, "heatmap",
                                   visuals.heatmap(change["difference_image"],
                                                   registration["overlap_mask"],
                                                   base_image=old_small)),
        "overlay": _write_artifact(output_dir, analysis_id, "overlay",
                                   visuals.contour_overlay(old_small, change["change_mask"])),
        "registered": _write_artifact(output_dir, analysis_id, "registered",
                                      visuals.registered_overlay(old_small,
                                                                 registration["registered"])),
        "side_by_side": _write_artifact(output_dir, analysis_id, "side_by_side",
                                        visuals.side_by_side(old_small, cv2.cvtColor(
                                            registration["registered"],
                                            cv2.COLOR_GRAY2BGR))),
    }
    artifacts_rel = {k: _as_relative(v) for k, v in artifacts.items()}

    # --- Land-use observations (Stage 5) --------------------------------------
    landuse_old = classify_landuse(old_small)
    landuse_new = classify_landuse(new_small)
    landuse_transitions = compare_landuse(landuse_old, landuse_new)
    landuse_segmentation = {
        "old": landuse_old["segmentation_png"],
        "new": landuse_new["segmentation_png"],
    }

    # --- Per-region records + explanations ------------------------------------
    valid_pixels = change["valid_pixels"]
    region_records = []
    for index, region in enumerate(change["regions"], start=1):
        region["priority"] = visuals.region_priority(
            region["pixel_area"], region["mean_intensity"], valid_pixels)
        region["detection_method"] = "difference thresholding + morphology"
        explanation = explain_region(region, index, change["change_percentage"],
                                     registration["stats"])
        region_records.append({**region, "explanation": explanation})

    priority_label, priority_breakdown = compute_priority(
        change_percentage=change["change_percentage"],
        boundary_iou=boundary_iou,
        image_quality={"quality_a": quality_old, "quality_b": quality_new},
        registration=registration["stats"],
        previous_changes=previous_changes,
    )

    if change["flag_suspicious"]:
        change_note = (
            "WARNING: the measured change covers almost the whole overlap - "
            "this usually means registration or illumination problems, not a "
            "real land change. Treat the result as unreliable."
        )
    else:
        change_note = None

    return {
        "status": "ok",
        "registration": registration["stats"],
        "quality": {"old": quality_old, "new": quality_new},
        "change": {
            "change_percentage": change["change_percentage"],
            "changed_pixels": change["changed_pixels"],
            "valid_pixels": change["valid_pixels"],
            "threshold_used": change["threshold_used"],
            "note": change_note,
        },
        "regions": region_records,
        "landuse": {
            "old": landuse_old["proportions"],
            "new": landuse_new["proportions"],
            "transitions": landuse_transitions,
            "method": landuse_old["method"],
            "segmentation": landuse_segmentation,
        },
        "priority": {"label": priority_label, "breakdown": priority_breakdown},
        "artifacts": artifacts_rel,
        "processing_seconds": round(time.time() - started, 2),
    }


def _as_relative(path):
    from config import BASE_DIR
    return Path(path).resolve().relative_to(BASE_DIR).as_posix()

"""
GeoSage - Image registration (Stage 3.2).

Aligns the recent image onto the previous image's frame using real
feature-based registration:

  ORB keypoints -> descriptor matching (Lowe ratio test) ->
  RANSAC homography -> perspective warp.

The module reports honest quality statistics and refuses to force an
alignment it cannot support:

- registration fails when too few features/matches exist (low-texture
  or unrelated scenes),
- it fails when the estimated transform is degenerate (extreme scale,
  flip, or translation) or the inlier ratio is too low,
- the caller decides what to do; nothing is silently faked.

No Flask imports - pure OpenCV/NumPy, unit-testable standalone.
"""
import cv2
import numpy as np

from modules.preprocessing import normalize_contrast, to_grayscale

# --- Honest, documented thresholds ------------------------------------------
# They are engineering choices for this mini-project, stated openly in the
# UI/docs rather than hidden inside the code.
MIN_KEYPOINTS = 60          # fewer ORB features than this -> too little texture
MIN_GOOD_MATCHES = 15       # fewer ratio-passing matches -> unreliable estimate
MIN_INLIERS = 10            # RANSAC inlier floor
MIN_INLIER_RATIO = 0.30     # below this the match set looks inconsistent
MAX_SCALE_RATIO = 2.5       # |scale| outside [1/2.5, 2.5] -> suspicious transform
MAX_TRANSLATION_FRACTION = 1.0  # shift larger than image size -> suspicious
MAX_MEDIAN_REPROJECTION_ERROR = 8.0  # pixels; larger -> poor alignment

ORB_FEATURES = 4000


def _sanity_check_homography(H, width, height):
    """Reject transforms no sensible capture-time difference can produce."""
    if H is None or not np.isfinite(H).all():
        return "Homography is degenerate or non-finite."

    scale_x = np.hypot(H[0, 0], H[1, 0])
    scale_y = np.hypot(H[0, 1], H[1, 1])
    if scale_x < 1e-9 or scale_y < 1e-9:
        return "Homography collapses one axis (invalid)."
    scale_ratio = max(scale_x, scale_y) / min(scale_x, scale_y)
    if scale_ratio > MAX_SCALE_RATIO:
        return f"Anisotropic scale ratio {scale_ratio:.2f} is implausible."
    if max(scale_x, scale_y) > MAX_SCALE_RATIO or max(scale_x, scale_y) < 1 / MAX_SCALE_RATIO:
        return f"Scale factor {max(scale_x, scale_y):.2f} is outside the plausible range."

    translation = abs(H[0, 2]) + abs(H[1, 2])
    if translation > MAX_TRANSLATION_FRACTION * max(width, height):
        return "Estimated translation is larger than the image itself."

    if H[2, 2] == 0:
        return "Homography perspective term is zero (invalid)."
    return None


def register_images(old_gray, new_gray):
    """Register `new_gray` into `old_gray`'s frame.

    Both inputs are single-channel uint8 arrays. Returns a result dict:

        success            bool
        reason             str  (only when success is False)
        homography         3x3 ndarray (only on success)
        registered         warped uint8 image aligned to `old_gray` (on success)
        overlap_mask       uint8 mask: pixels of `old_gray` covered by the
                           warped recent image (on success)
        stats              dict of real measured values
    """
    stats = {
        "keypoints_old": 0, "keypoints_new": 0,
        "good_matches": 0, "inliers": 0, "inlier_ratio": 0.0,
        "median_reprojection_error": None,
        "method": "ORB + RANSAC homography",
    }

    # Contrast normalization first: keypoint repeatability improves when the
    # two captures do not differ too much in global illumination.
    old_eq = normalize_contrast(old_gray)
    new_eq = normalize_contrast(new_gray)

    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    kp_old, des_old = orb.detectAndCompute(old_eq, None)
    kp_new, des_new = orb.detectAndCompute(new_eq, None)
    stats["keypoints_old"] = 0 if kp_old is None else len(kp_old)
    stats["keypoints_new"] = 0 if kp_new is None else len(kp_new)

    if stats["keypoints_old"] < MIN_KEYPOINTS or stats["keypoints_new"] < MIN_KEYPOINTS:
        stats["failure_stage"] = "feature_detection"
        return {"success": False,
                "reason": ("Not enough distinctive image features to align the "
                           "pair (low texture or unrelated scenes). "
                           f"Features found: {stats['keypoints_old']} / "
                           f"{stats['keypoints_new']}; at least {MIN_KEYPOINTS} "
                           "per image is required."),
                "stats": stats}

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = matcher.knnMatch(des_new, des_old, k=2)  # match recent -> previous
    good = []
    for pair in raw_matches:
        if len(pair) == 2:  # Lowe ratio test on the two nearest neighbours
            best, second = pair
            if best.distance < 0.75 * second.distance:
                good.append(best)
    stats["good_matches"] = len(good)

    if len(good) < MIN_GOOD_MATCHES:
        stats["failure_stage"] = "matching"
        return {"success": False,
                "reason": (f"Only {len(good)} reliable feature matches found "
                           f"({MIN_GOOD_MATCHES} required). The images may not "
                           "overlap or may look too different."),
                "stats": stats}

    src_pts = np.float32([kp_new[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_old[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    H, inlier_mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    inliers = int(inlier_mask.sum()) if inlier_mask is not None else 0
    inlier_ratio = inliers / len(good) if good else 0.0
    stats["inliers"] = inliers
    stats["inlier_ratio"] = round(float(inlier_ratio), 3)

    if H is None or inliers < MIN_INLIERS or inlier_ratio < MIN_INLIER_RATIO:
        stats["failure_stage"] = "ransac"
        return {"success": False,
                "reason": ("Feature matches are geometrically inconsistent "
                           f"({inliers} inliers, ratio {inlier_ratio:.2f}; "
                           f"minimum {MIN_INLIERS} / {MIN_INLIER_RATIO:.2f}). "
                           "The images likely do not depict the same area."),
                "stats": stats}

    problem = _sanity_check_homography(H, old_gray.shape[1], old_gray.shape[0])
    if problem:
        stats["failure_stage"] = "sanity_check"
        return {"success": False, "reason": problem, "stats": stats}

    # --- Reprojection error: median residual of RANSAC inliers ---------------
    projected = cv2.perspectiveTransform(src_pts, H)
    residuals = np.linalg.norm(projected.reshape(-1, 2) - dst_pts.reshape(-1, 2), axis=1)
    inlier_residuals = residuals[inlier_mask.ravel().astype(bool)]
    median_error = float(np.median(inlier_residuals)) if inlier_residuals.size else None
    stats["median_reprojection_error"] = round(median_error, 2) if median_error is not None else None

    if median_error is not None and median_error > MAX_MEDIAN_REPROJECTION_ERROR:
        stats["failure_stage"] = "reprojection"
        return {"success": False,
                "reason": (f"Alignment error too high (median reprojection "
                           f"{median_error:.1f}px > {MAX_MEDIAN_REPROJECTION_ERROR}px). "
                           "The registered comparison would be unreliable."),
                "stats": stats}

    h, w = old_gray.shape[:2]
    registered = cv2.warpPerspective(new_gray, H, (w, h), flags=cv2.INTER_LINEAR,
                                     borderValue=0)

    # Overlap mask: where the warped recent image actually has data.
    ones = np.ones_like(new_gray, dtype=np.uint8) * 255
    overlap_mask = cv2.warpPerspective(ones, H, (w, h), flags=cv2.INTER_NEAREST,
                                       borderValue=0)

    return {"success": True, "homography": H, "registered": registered,
            "overlap_mask": overlap_mask, "stats": stats}

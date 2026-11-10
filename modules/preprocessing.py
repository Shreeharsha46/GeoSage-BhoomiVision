"""
GeoSage - Image preprocessing (Stage 3.1).

Pure NumPy/OpenCV helpers with no Flask dependency so the algorithms can
be unit-tested and reused independently of the web application.

Responsibilities:
- decode image bytes safely (Unicode-safe on Windows paths),
- dimension validation,
- downscaling for memory-efficient analysis,
- grayscale conversion and contrast normalization,
- a simple image-quality assessment (blur / brightness / contrast) whose
  values feed the review-priority engine and explanations.
"""
import cv2
import numpy as np

from routes.uploads import MIN_DIMENSION  # single source of truth for limits


class ImageError(Exception):
    """Raised when an image cannot be decoded or is unusable."""


def decode_bytes(data):
    """Decode raw image bytes to a BGR ndarray (raises ImageError on failure).

    cv2.imdecode is used instead of imread so Unicode paths work on
    Windows and the bytes have already passed upload validation.
    """
    if not data:
        raise ImageError("No image data supplied.")
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ImageError("The image could not be decoded.")
    return image


def load_stored(path):
    """Load an image from a project-relative stored path."""
    try:
        with open(path, "rb") as handle:
            return decode_bytes(handle.read())
    except FileNotFoundError as exc:
        raise ImageError(f"Image file missing on disk: {path}") from exc


def validate_dimensions(image, min_dimension=MIN_DIMENSION):
    """Reject images below the useful-analysis size."""
    height, width = image.shape[:2]
    if height < min_dimension or width < min_dimension:
        raise ImageError(
            f"Image too small for analysis ({width}x{height}); minimum is "
            f"{min_dimension}x{min_dimension}."
        )
    return width, height


def downscale(image, max_width):
    """Resize so width <= max_width, keeping the aspect ratio."""
    height, width = image.shape[:2]
    if width <= max_width:
        return image
    scale = max_width / width
    new_size = (max_width, max(1, int(round(height * scale))))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def to_grayscale(image):
    """BGR -> single-channel grayscale."""
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def normalize_contrast(gray):
    """CLAHE contrast normalization.

    Limits the influence of global illumination differences (sun angle,
    shadows) between capture dates while keeping local contrast that the
    change detector needs. This is a mitigation, not a guarantee - strong
    shadows still affect results (documented limitation).
    """
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def assess_quality(gray):
    """Return basic quality indicators for one grayscale image.

    - blur_score: variance of the Laplacian. Higher = sharper. There is no
      universal threshold, so the raw value is stored and interpreted in
      relative terms only.
    - brightness: mean intensity 0-255.
    - contrast: standard deviation of intensities.
    """
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    return {
        "blur_score": round(blur_score, 2),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
    }

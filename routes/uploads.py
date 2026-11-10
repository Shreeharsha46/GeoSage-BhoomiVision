"""
Upload validation and safe storage.

Security measures implemented here:
- extension whitelist AND real content sniffing via Pillow (a renamed
  .exe will not pass),
- maximum file size enforcement,
- decompression-bomb protection (Pillow's MAX_IMAGE_PIXELS guard),
- minimum/maximum image dimension checks,
- generated random filenames (user input never becomes a path),
- files stored under uploads/ which is NOT served statically - access
  goes through permission-checked routes only.
"""
import uuid
from io import BytesIO

from PIL import Image

Image.MAX_IMAGE_PIXELS = 50_000_000  # ~50 MP guard against decompression bombs

MAX_UPLOAD_BYTES = 32 * 1024 * 1024  # must match MAX_CONTENT_LENGTH in config
MIN_DIMENSION = 64
MAX_DIMENSION = 12_000

PIL_FORMAT_BY_EXT = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "tif": "TIFF", "tiff": "TIFF",
}


class UploadError(Exception):
    """Raised with a user-facing message when an upload is rejected."""


def validate_image(data, filename, allowed_extensions):
    """Validate raw upload bytes. Returns the Pillow-confirmed format.

    Raises UploadError with a user-facing message on any problem.
    """
    if not data:
        raise UploadError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("File is larger than the 32 MB limit.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise UploadError(
            f"Unsupported file type '.{ext}'. Allowed: "
            + ", ".join(sorted(allowed_extensions))
        )

    try:
        with Image.open(BytesIO(data)) as probe:
            real_format = probe.format
            probe.verify()  # detects truncated/corrupt files
    except Image.DecompressionBombError:
        raise UploadError("Image dimensions are dangerously large (decompression bomb guard).")
    except Exception:
        raise UploadError("The file could not be decoded as an image (corrupt or not an image).")

    if real_format != PIL_FORMAT_BY_EXT.get(ext):
        raise UploadError(
            f"File content ({real_format or 'unknown'}) does not match its '.{ext}' extension."
        )

    # Re-open (verify() invalidates the image) to check dimensions.
    with Image.open(BytesIO(data)) as img:
        width, height = img.size
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise UploadError(f"Image too small ({width}x{height}); minimum is "
                          f"{MIN_DIMENSION}x{MIN_DIMENSION} pixels.")
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise UploadError(f"Image too large ({width}x{height}); maximum is "
                          f"{MAX_DIMENSION}x{MAX_DIMENSION} pixels.")
    return real_format


def generate_stored_name(extension):
    """Random, safe filename - original user filenames are never used on disk."""
    return f"{uuid.uuid4().hex}.{extension.lower()}"

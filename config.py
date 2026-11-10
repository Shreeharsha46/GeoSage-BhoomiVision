"""
GeoSage - Application configuration.

All paths, limits and feature flags live in this single file so the rest
of the code never hard-codes locations. Sensitive values (secret key,
database URL) can be overridden through a local .env file - see .env.example.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root (the folder that contains this file)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base configuration shared by every environment."""

    # --- Core Flask settings ---------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024          # 32 MB maximum upload size

    # --- CSRF protection (Flask-WTF) ---------------------------------------
    WTF_CSRF_ENABLED = True

    # Seed the two demo accounts on first run (disabled under testing)
    SEED_DEMO_USERS = True

    # --- Database ----------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'database' / 'geosage.db').as_posix()}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Upload / output directories ---------------------------------------
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    OUTPUT_FOLDER = BASE_DIR / "outputs"

    OLD_IMAGE_FOLDER = UPLOAD_FOLDER / "old_images"
    RECENT_IMAGE_FOLDER = UPLOAD_FOLDER / "recent_images"
    BOUNDARY_FOLDER = UPLOAD_FOLDER / "boundaries"

    HEATMAP_FOLDER = OUTPUT_FOLDER / "heatmaps"
    MASK_FOLDER = OUTPUT_FOLDER / "masks"
    REPORT_FOLDER = OUTPUT_FOLDER / "reports"

    # --- Validation rules ----------------------------------------------------
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "tif", "tiff"}
    ALLOWED_BOUNDARY_EXTENSIONS = {"geojson", "json", "kml"}

    # --- Analysis engine limits ---------------------------------------------
    # Large images are downscaled before CV work so analyses stay fast
    # on a normal Windows laptop.
    MAX_ANALYSIS_WIDTH = 1600

    # --- File storage backend ----------------------------------------------
    # Options: "local" (default), "s3", "r2"
    # For production on Render free tier, use cloud storage (S3/R2)
    # Local filesystem is ephemeral on Render - files lost on deploy
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")

    # Cloud storage credentials (set in production env)
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
    # For Cloudflare R2, use S3-compatible endpoint
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")


class DevelopmentConfig(Config):
    """Local development - interactive debugger enabled."""
    DEBUG = True


class TestingConfig(Config):
    """Automated tests - isolated in-memory database, no files on disk."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # let tests POST directly
    SEED_DEMO_USERS = False   # tests create their own users


class ProductionConfig(Config):
    """Deployment profile - debugger disabled, secure defaults."""
    DEBUG = False
    TESTING = False
    # Ensure SECRET_KEY is set via environment in production
    SEED_DEMO_USERS = False  # Don't auto-create demo accounts in production


# Name used in FLASK_CONFIG environment variable -> config class
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
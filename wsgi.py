"""
Production WSGI entry point for GeoSage.

Used by gunicorn in production:
    gunicorn -c gunicorn.conf.py wsgi:app

Or directly:
    gunicorn wsgi:app
"""
import os
from app import create_app

# Determine config from environment; default to production
config_name = os.environ.get("FLASK_CONFIG", "production")
app = create_app(config_name)

if __name__ == "__main__":
    # Allow running directly for quick testing: python wsgi.py
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
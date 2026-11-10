"""
GeoSage - AI-Powered Rural Land Intelligence & Boundary Verification System.
Platform branding: BHOOMI VISION.

Application entry point.

`create_app()` follows the application-factory pattern so tests can build
isolated app instances with their own in-memory database (see tests/).

Run the development server from the project folder:

    python app.py            ->  http://127.0.0.1:5000
"""
import os
from datetime import datetime
from pathlib import Path

import click
from flask import Flask
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from config import config_by_name
from database.db import db
from database.migrations import run_migrations

csrf = CSRFProtect()

# Directory config keys that must exist before anything is uploaded/processed
FOLDER_KEYS = (
    "UPLOAD_FOLDER", "OUTPUT_FOLDER",
    "OLD_IMAGE_FOLDER", "RECENT_IMAGE_FOLDER", "BOUNDARY_FOLDER",
    "HEATMAP_FOLDER", "MASK_FOLDER", "REPORT_FOLDER",
)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access GeoSage."
login_manager.login_message_category = "warning"


def ensure_folders(app):
    """Create all upload/output directories on first run (idempotent)."""
    for key in FOLDER_KEYS:
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)


def seed_demo_users(app):
    """Create demo accounts on first run so the app is demonstrable at once.

    Public registration always creates 'analyst' accounts; the seeded
    admin demonstrates the administrator role for the viva demo.
    Skipped in testing mode (tests create their own users).
    """
    if not app.config.get("SEED_DEMO_USERS", True):
        return
    from database.models import User
    if db.session.query(User).count() > 0:
        return
    admin = User(name="Administrator", email="admin@geosage.test", role="admin")
    admin.set_password("Admin@1234")
    analyst = User(name="Demo Analyst", email="analyst@geosage.test", role="analyst")
    analyst.set_password("Analyst@1234")
    db.session.add_all([admin, analyst])
    db.session.commit()
    print("Seeded demo accounts: admin@geosage.test / Admin@1234 | "
          "analyst@geosage.test / Analyst@1234")


def register_blueprints(app):
    """Register every feature blueprint (extended stage by stage)."""
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.parcels import media_bp, parcels_bp
    from routes.settings import settings_bp
    from routes.admin import admin_bp
    from routes.analysis import analysis_bp
    from routes.boundaries import boundaries_bp
    from routes.landuse import landuse_bp
    from routes.history import history_bp
    from routes.reviews import reviews_bp
    from routes.reports import reports_bp
    from routes.assistant import assistant_bp

    for blueprint in (main_bp, auth_bp, parcels_bp, media_bp, settings_bp,
                      admin_bp, analysis_bp, boundaries_bp, landuse_bp,
                      history_bp, reviews_bp, reports_bp, assistant_bp):
        app.register_blueprint(blueprint)


def create_app(config_name=None):
    """Build and configure the Flask application."""
    app = Flask(__name__)
    config_name = config_name or os.environ.get("FLASK_CONFIG", "development")
    app.config.from_object(config_by_name[config_name])

    ensure_folders(app)

    # --- Extensions ---------------------------------------------------------
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from database.models import User
        return db.session.get(User, int(user_id))

    # --- Blueprints ------------------------------------------------------------
    register_blueprints(app)

    # --- Template globals --------------------------------------------------------
    @app.context_processor
    def inject_globals():
        return {"current_year": datetime.now().year}

    # --- Database ------------------------------------------------------------
    with app.app_context():
        import database.models  # noqa: F401  (model classes must be imported)

        db.create_all()      # creates missing tables
        run_migrations(app)  # adds new columns to existing tables (additive only)
        seed_demo_users(app)

    # --- CLI helper ------------------------------------------------------------
    @app.cli.command("init-db")
    def init_db_command():
        """Create all database tables (flask --app app init-db)."""
        db.create_all()
        run_migrations(app)
        click.echo("Database initialized.")

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host="127.0.0.1",
        port=5000,
        debug=application.config["DEBUG"],
        # Set FLASK_RELOADER=0 to disable the auto-reload watcher
        use_reloader=os.environ.get("FLASK_RELOADER", "1") == "1",
    )

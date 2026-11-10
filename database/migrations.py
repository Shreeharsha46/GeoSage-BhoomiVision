"""
Additive schema migrations for existing SQLite databases.

`db.create_all()` creates missing TABLES but never alters existing ones.
This module applies additive `ALTER TABLE ... ADD COLUMN` statements so an
existing Stage-1 database is upgraded in place without any data loss.
Each statement runs only when its column is still missing; nothing is
ever dropped or recreated.
"""
from sqlalchemy import inspect, text

from database.db import db

# (table, column, full ALTER statement)
MIGRATIONS = [
    ("users", "is_active",
     "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"),
    ("analysis_results", "processing_metadata",
     "ALTER TABLE analysis_results ADD COLUMN processing_metadata TEXT"),
    ("analysis_results", "artifacts",
     "ALTER TABLE analysis_results ADD COLUMN artifacts TEXT"),
    ("analysis_results", "review_priority",
     "ALTER TABLE analysis_results ADD COLUMN review_priority VARCHAR(10)"),
    ("analysis_results", "boundary_summary",
     "ALTER TABLE analysis_results ADD COLUMN boundary_summary TEXT"),
    ("detected_regions", "bbox",
     "ALTER TABLE detected_regions ADD COLUMN bbox TEXT"),
    ("detected_regions", "centroid",
     "ALTER TABLE detected_regions ADD COLUMN centroid TEXT"),
    ("detected_regions", "mean_intensity",
     "ALTER TABLE detected_regions ADD COLUMN mean_intensity FLOAT"),
    ("detected_regions", "detection_method",
     "ALTER TABLE detected_regions ADD COLUMN detection_method VARCHAR(50)"),
    ("review_records", "previous_status",
     "ALTER TABLE review_records ADD COLUMN previous_status VARCHAR(40)"),
    ("boundary_records", "source",
     "ALTER TABLE boundary_records ADD COLUMN source VARCHAR(20) DEFAULT 'upload'"),
    ("boundary_records", "space",
     "ALTER TABLE boundary_records ADD COLUMN space VARCHAR(20) DEFAULT 'geographic'"),
    ("boundary_records", "geometry_json",
     "ALTER TABLE boundary_records ADD COLUMN geometry_json TEXT"),
    ("boundary_records", "label",
     "ALTER TABLE boundary_records ADD COLUMN label VARCHAR(120)"),
    ("boundary_records", "comparison_json",
     "ALTER TABLE boundary_records ADD COLUMN comparison_json TEXT"),
]


def run_migrations(app):
    """Apply pending additive migrations; safe to run on every startup."""
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        applied = 0
        for table, column, ddl in MIGRATIONS:
            if table not in existing_tables:
                continue  # fresh table: create_all() builds it with all columns
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column not in columns:
                db.session.execute(text(ddl))
                db.session.commit()
                app.logger.info("Migration applied: %s", ddl)
                applied += 1
        if applied:
            print(f"Database upgraded: {applied} migration(s) applied.")

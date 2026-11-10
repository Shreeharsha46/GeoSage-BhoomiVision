"""
Shared pytest fixtures for GeoSage tests.

Every test gets a fresh application with an isolated in-memory SQLite
database, so tests never touch the real development database on disk.
"""
import pytest

from app import create_app
from database.db import db
from database.models import User

# Standard test accounts (mirroring the seeded demo accounts used in dev mode)
ANALYST_EMAIL = "analyst@geosage.test"
ANALYST_PASSWORD = "Analyst@1234"
ADMIN_EMAIL = "admin@geosage.test"
ADMIN_PASSWORD = "Admin@1234"


def make_test_users():
    analyst = User(name="Test Analyst", email=ANALYST_EMAIL, role="analyst")
    analyst.set_password(ANALYST_PASSWORD)
    admin = User(name="Test Admin", email=ADMIN_EMAIL, role="admin")
    admin.set_password(ADMIN_PASSWORD)
    db.session.add_all([analyst, admin])
    db.session.commit()


@pytest.fixture()
def app():
    """Fresh isolated app with an empty in-memory database per test.

    NOTE: the app context must NOT be held open across client requests.
    Flask-Login caches the authenticated user on the app context's `g`,
    so a context spanning several requests would leak one client's login
    state into later requests (an anonymous client would be treated as
    logged in). Setup/teardown each use their own short-lived context.
    """
    application = create_app(config_name="testing")
    with application.app_context():
        db.create_all()
        make_test_users()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client bound to the isolated app."""
    return app.test_client()

"""
Stage 2 tests: registration, login, logout, protected routes, roles.

Covers specification test items 1-8 (registration, duplicate e-mail,
password login, wrong password, logout, protected routes, admin and
analyst permissions).
"""
import pytest

from database.db import db
from database.models import User

NEW_USER = dict(name="Test Analyst", email="tester@geosage.test",
                password="Passw0rd123", confirm="Passw0rd123")


@pytest.fixture()
def client(app):
    """Seeded app: the factory creates the two demo accounts."""
    return app.test_client()


def login(client, email="analyst@geosage.test", password="Analyst@1234"):
    return client.post("/login", data={"email": email, "password": password},
                       follow_redirects=True)


def register(client, **overrides):
    data = dict(NEW_USER)
    data.update(overrides)
    return client.post("/register", data=data, follow_redirects=True)


# --- 1. Successful registration ------------------------------------------------

def test_registration_success(app, client):
    response = register(client)
    assert response.status_code == 200
    with app.app_context():
        user = db.session.query(User).filter_by(email="tester@geosage.test").first()
        assert user is not None
        assert user.role == "analyst"          # public registration is always analyst
        assert user.check_password("Passw0rd123")
    assert b"Dashboard" in response.data       # logged in and redirected


# --- 2. Duplicate e-mail rejection ----------------------------------------------

def test_duplicate_email_rejected(client):
    register(client)
    client.get("/logout")  # log out so we can register again
    response = register(client)
    assert b"already exists" in response.data


# --- 3/4. Login with correct / incorrect password --------------------------------

def test_login_correct_password(client):
    response = login(client)
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_login_wrong_password_rejected(client):
    response = login(client, password="WrongPass1")
    assert b"Invalid e-mail or password" in response.data


def test_password_strength_enforced(client):
    client.get("/logout")
    response = register(client, password="short1", confirm="short1")     # too short
    assert b"at least 8 characters" in response.data
    response = register(client, password="onlyletters", confirm="onlyletters")
    assert b"at least one digit" in response.data


# --- 5. Logout ----------------------------------------------------------------------

def test_logout(client):
    login(client)
    client.get("/logout")
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302          # bounced to the login page


# --- 6. Protected routes require login ------------------------------------------------

@pytest.mark.parametrize("path", ["/dashboard", "/parcels/", "/settings/"])
def test_protected_routes_redirect_anonymous(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- 7/8. Admin vs analyst permissions ------------------------------------------------

def test_admin_sees_manage_users_and_all_data(client):
    login(client, email="admin@geosage.test", password="Admin@1234")
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert b"authorized users" in response.data.lower()


def test_analyst_cannot_access_admin_routes(client):
    login(client)
    response = client.get("/admin/users", follow_redirects=True)
    assert b"Administrator access required" in response.data


def test_deactivated_user_cannot_login(app, client):
    with app.app_context():
        user = db.session.query(User).filter_by(email="analyst@geosage.test").first()
        user.is_active = False
        db.session.commit()
    response = login(client)
    assert b"deactivated" in response.data

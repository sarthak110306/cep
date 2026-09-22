"""Login / signup tests. These exercise validation and control flow using
a fake in-memory DB layer (see conftest.py) - they do not touch a real
MySQL database."""
from werkzeug.security import generate_password_hash

from conftest import get_csrf_token


def test_login_rejects_missing_fields(client, fake_db):
    token = get_csrf_token(client, "/login")
    resp = client.post(
        "/login",
        data={"email": "", "password": "", "csrf_token": token},
    )
    assert resp.status_code == 302  # redirected back with a flash error


def test_login_rejects_wrong_password(client, fake_db):
    fake_db.queue_fetchone({
        "id": 1,
        "name": "Test User",
        "email": "user@example.com",
        "password_hash": generate_password_hash("correct-password"),
    })
    token = get_csrf_token(client, "/login")
    resp = client.post(
        "/login",
        data={"email": "user@example.com", "password": "wrong-password", "csrf_token": token},
        follow_redirects=True,
    )
    assert b"Invalid email or password" in resp.data


def test_login_succeeds_with_correct_credentials(client, fake_db):
    fake_db.queue_fetchone({
        "id": 1,
        "name": "Test User",
        "email": "user@example.com",
        "password_hash": generate_password_hash("correct-password"),
    })
    token = get_csrf_token(client, "/login")
    resp = client.post(
        "/login",
        data={"email": "user@example.com", "password": "correct-password", "csrf_token": token},
    )
    assert resp.status_code == 302
    assert "/home" in resp.headers["Location"]


def test_signup_rejects_password_mismatch(client, fake_db):
    token = get_csrf_token(client, "/login")
    resp = client.post(
        "/signup",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "password1",
            "confirm_password": "password2",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert b"Passwords do not match" in resp.data


def test_signup_rejects_short_password(client, fake_db):
    token = get_csrf_token(client, "/login")
    resp = client.post(
        "/signup",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "ab",
            "confirm_password": "ab",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert b"at least 5 characters" in resp.data


def test_signup_rejects_invalid_email(client, fake_db):
    token = get_csrf_token(client, "/login")
    resp = client.post(
        "/signup",
        data={
            "name": "New User",
            "email": "not-an-email",
            "password": "password1",
            "confirm_password": "password1",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert b"valid email" in resp.data

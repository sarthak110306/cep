"""Issue #2 - CSRF protection tests."""
from conftest import get_csrf_token


def test_post_without_csrf_token_is_rejected(client, fake_db):
    """A POST with no csrf_token field at all must be rejected (400)."""
    resp = client.post(
        "/login",
        data={"email": "someone@example.com", "password": "whatever"},
    )
    assert resp.status_code == 400


def test_post_with_wrong_csrf_token_is_rejected(client, fake_db):
    resp = client.post(
        "/login",
        data={
            "email": "someone@example.com",
            "password": "whatever",
            "csrf_token": "this-is-not-a-real-token",
        },
    )
    assert resp.status_code == 400


def test_post_with_valid_csrf_token_is_accepted(client, fake_db):
    """A POST with the real token issued for this session must be let
    through to the view (it may still fail login for other reasons, but it
    must NOT be rejected at the CSRF layer with a 400)."""
    token = get_csrf_token(client, "/login")

    # No matching user in the fake DB -> view runs, login fails "normally"
    # (redirect), which proves CSRF was accepted (a CSRF failure would be
    # a 400, not a redirect).
    resp = client.post(
        "/login",
        data={
            "email": "nobody@example.com",
            "password": "wrongpassword",
            "csrf_token": token,
        },
    )
    assert resp.status_code == 302


def test_contact_form_requires_csrf(client, fake_db):
    resp = client.post(
        "/contact",
        data={
            "name": "Test",
            "email": "test@example.com",
            "subject": "Hi",
            "message": "Hello there",
        },
    )
    assert resp.status_code == 400

"""Issue #6 - server-side team size validation, and Issue #8 - registration
ID generation."""
from conftest import get_csrf_token


def _login_session(client, user_id=1):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Test User"


def _base_team_form(token, **overrides):
    data = {
        "team_name": "Team Alpha",
        "college": "Test College",
        "leader_name": "Leader Name",
        "phone": "9876543210",
        "email": "leader@example.com",
        "problem_statement_id": "1",
        "csrf_token": token,
    }
    data.update(overrides)
    return data


def test_team_registration_rejects_zero_additional_members(client, fake_db):
    _login_session(client)
    token = get_csrf_token(client, "/team-registration")
    resp = client.post(
        "/team-registration",
        data=_base_team_form(token, members=[]),
        follow_redirects=True,
    )
    assert b"between 2 and 4 members" in resp.data


def test_team_registration_rejects_too_many_members(client, fake_db):
    """4 additional members + leader = 5 total -> must be rejected
    (max is leader + 3 = 4 total)."""
    _login_session(client)
    token = get_csrf_token(client, "/team-registration")
    resp = client.post(
        "/team-registration",
        data={
            **_base_team_form(token),
            "members": ["Member One", "Member Two", "Member Three", "Member Four"],
        },
        follow_redirects=True,
    )
    assert b"between 2 and 4 members" in resp.data


def test_team_registration_accepts_valid_team_size(client, fake_db):
    """1 to 3 additional members (2-4 total) must pass the size check and
    reach the database-write step (no existing team/registration rows in
    the fake DB, so it should insert and redirect onward)."""
    _login_session(client)
    token = get_csrf_token(client, "/team-registration")
    resp = client.post(
        "/team-registration",
        data={
            **_base_team_form(token),
            "members": ["Member One", "Member Two"],
        },
    )
    # Should redirect to judges-mentors on success, NOT bounce back to
    # team-registration with a size-validation error.
    assert resp.status_code == 302
    assert "team-registration" not in resp.headers["Location"]


def test_team_registration_rejects_invalid_phone(client, fake_db):
    _login_session(client)
    token = get_csrf_token(client, "/team-registration")
    resp = client.post(
        "/team-registration",
        data={
            **_base_team_form(token, phone="12345"),
            "members": ["Member One"],
        },
        follow_redirects=True,
    )
    assert b"valid 10-digit phone number" in resp.data


def test_generate_registration_id_format(app_module):
    assert app_module.generate_registration_id(1) == "HACK2026-00001"
    assert app_module.generate_registration_id(42) == "HACK2026-00042"
    assert app_module.generate_registration_id(100000) == "HACK2026-100000"


def test_generate_registration_id_is_unique_per_row(app_module):
    """Issue #8 - two different registration rows must never produce the
    same ID (the old COUNT()+1 approach could collide under concurrency;
    id-based generation cannot, since primary keys are unique by
    definition)."""
    ids = {app_module.generate_registration_id(i) for i in range(1, 51)}
    assert len(ids) == 50

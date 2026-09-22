"""Issue #14 - rate limiting behavior test.

login/admin_login are limited to 10 POSTs/minute. This test drives more
than that through the same client and expects a 429 once the limit is
exceeded, proving the limiter is actually wired in (not just imported).
"""
from conftest import get_csrf_token


def test_login_is_rate_limited_after_repeated_attempts(client, fake_db):
    token = get_csrf_token(client, "/login")

    statuses = []
    for _ in range(15):
        resp = client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "wrong", "csrf_token": token},
        )
        statuses.append(resp.status_code)

    # The first several requests should be handled normally (302 redirect
    # on invalid credentials); at some point Flask-Limiter must start
    # returning 429 Too Many Requests.
    assert 429 in statuses, (
        "Expected a 429 Too Many Requests once the login rate limit "
        f"(10/minute) was exceeded, got statuses: {statuses}"
    )
    # And normal usage (a handful of attempts) must NOT be blocked -
    # rate limiting shouldn't make ordinary usage difficult.
    assert statuses[0] == 302

# Test Suite

## How to run

From the project root (`C:\manus code`), with your virtual environment
active and dependencies installed:

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -v
```

## What this covers

- Application import/startup with no errors (`test_app_startup.py`)
- Debug mode defaults to off, session cookie security settings, CSRF and
  rate-limiter presence (`test_app_startup.py`)
- CSRF protection: rejects missing/invalid tokens, accepts a real token
  (`test_csrf.py`)
- Login/signup validation and control flow (`test_auth.py`)
- Team size validation (2-4 members total) - rejects 1-member and 5-member
  teams, accepts 2-4 member teams (`test_team_and_registration_id.py`)
- Registration ID generation format and uniqueness (`test_team_and_registration_id.py`)
- Rate limiting actually triggers a 429 after repeated login attempts
  (`test_rate_limiting.py`)

## What this does NOT cover (important limitation)

**These tests do not use a real MySQL database.** `tests/conftest.py`
replaces `app.py`'s database layer with an in-memory fake (`FakeCursor`/
`FakeConnection`) so the suite can run anywhere without MySQL installed or
configured.

This means the tests verify **application logic** - validation rules,
CSRF enforcement, redirects, rate limiting, ID generation - but they do
**not** prove that real SQL statements against your actual
`community_hackathon` database succeed, that foreign key constraints
behave as expected, or that data is actually persisted correctly.

To fully verify database behavior, you should also manually test the
application end-to-end against a real MySQL database (the "Verify..."
checklist in the project report covers this). Similarly, no email/SMTP
functionality is tested here (none currently exists in the app - the
OTP-based email flow was removed).

## Adding more tests

Keep new tests focused and practical - this suite intentionally does not
try to test every line of `app.py`. Add a test when you fix a bug or add
validation, following the existing pattern of mocking `get_db_connection`/
`dict_cursor` via the `fake_db` fixture in `conftest.py`.

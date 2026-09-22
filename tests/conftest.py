"""
Shared pytest fixtures.

IMPORTANT: These tests run WITHOUT a real MySQL server. A fake in-memory
cursor/connection is used so route logic (validation, CSRF, rate limiting,
redirects) can be exercised without a live database or SMTP credentials.

This means these tests verify application LOGIC, not actual data
persistence against MySQL. They deliberately do NOT prove the app works
against your real database - only that its request/response/validation
behavior is correct. See tests/README_TESTS.md.
"""
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Stub out mysql.connector before app.py (and database/db.py) import it, so
# the test suite can run without a MySQL server or driver installed.
# ---------------------------------------------------------------------------
if "mysql.connector" not in sys.modules:
    mysql_module = types.ModuleType("mysql")
    connector_module = types.ModuleType("mysql.connector")

    class _DummyError(Exception):
        pass

    def _connect(**kwargs):
        raise _DummyError("No real database available in the test environment.")

    connector_module.Error = _DummyError
    connector_module.connect = _connect
    mysql_module.connector = connector_module
    sys.modules["mysql"] = mysql_module
    sys.modules["mysql.connector"] = connector_module


class FakeCursor:
    """A minimal stand-in for a mysql-connector dictionary cursor.

    Queue up return values with `queue_fetchone`/`queue_fetchall` before
    the route runs; anything not queued returns None / [] so simple
    validation-only tests (e.g. "reject an invalid team size before ever
    touching real data") don't need to configure anything.
    """

    def __init__(self):
        self.executed = []
        self._fetchone_queue = []
        self._fetchall_queue = []
        self.lastrowid = 1

    def queue_fetchone(self, value):
        self._fetchone_queue.append(value)

    def queue_fetchall(self, value):
        self._fetchall_queue.append(value)

    def execute(self, sql, params=None):
        self.executed.append((sql.strip(), params))

    def fetchone(self):
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None

    def fetchall(self):
        if self._fetchall_queue:
            return self._fetchall_queue.pop(0)
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def app_module():
    """Import app.py fresh for each test module needing it."""
    import importlib
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as appmod
    importlib.reload(appmod)
    appmod.app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    return appmod


@pytest.fixture
def fake_db(app_module, monkeypatch):
    """Patch app.py's DB access with an in-memory fake. Returns the
    FakeCursor so a test can pre-load fetchone/fetchall responses."""
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(app_module, "get_db_connection", lambda: connection)
    monkeypatch.setattr(app_module, "dict_cursor", lambda conn: conn.cursor())
    return cursor


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


def get_csrf_token(client, get_url):
    """GET a page that renders a CSRF meta/hidden-input token and pull the
    token value out of the HTML, using the same test client (so the
    session cookie set on this GET matches the token)."""
    import re
    resp = client.get(get_url)
    html = resp.get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, f"Could not find a CSRF token on {get_url}"
    return match.group(1)

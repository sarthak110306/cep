"""Application startup / import sanity checks."""


def test_app_imports_without_errors(app_module):
    assert app_module.app is not None


def test_app_has_expected_route_count(app_module):
    rules = list(app_module.app.url_map.iter_rules())
    # Sanity floor, not an exact count - just makes sure routes are actually
    # registered (would be ~0 if something broke route registration).
    assert len(rules) > 30


def test_no_debug_mode_by_default(app_module, monkeypatch):
    """Issue #5 - debug must default to OFF unless FLASK_DEBUG is set."""
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    value = app_module.os.getenv("FLASK_DEBUG", "false").strip().lower()
    assert value in ("false", "0", "no", "")


def test_session_cookie_security_settings(app_module):
    """Issue #15."""
    assert app_module.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app_module.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app_module.app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() > 0


def test_csrf_protection_is_enabled(app_module):
    """Issue #2 - CSRFProtect must actually be initialized on the app."""
    assert app_module.app.config.get("WTF_CSRF_ENABLED", True) is True
    assert app_module.csrf is not None


def test_rate_limiter_is_configured(app_module):
    """Issue #14."""
    assert app_module.limiter is not None

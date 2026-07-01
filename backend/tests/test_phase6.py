"""Phase 6 tests — security hardening: CORS allowlist + production secrets guard.

CORS is now an explicit origin allowlist (no more ``*`` + credentials). The
secrets guard refuses to boot a non-SQLite DB with the default JWT secret
(opt-out via ``ALLOW_INSECURE_SECRETS`` for an ephemeral demo).
"""

from __future__ import annotations

import pytest
from clin_doc.settings import (
    assert_production_secrets,
    cors_origin_list,
    get_settings,
)


def test_cors_origin_list_parses_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("CORS_ORIGINS", "https://demo.example.com, https://staging.example.com")
    assert cors_origin_list() == ["https://demo.example.com", "https://staging.example.com"]


def test_cors_origin_list_single(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    assert cors_origin_list() == ["http://localhost:3000"]


def test_cors_origin_list_drops_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, , ")
    assert cors_origin_list() == ["http://localhost:3000"]


def test_assert_production_secrets_rejects_default_on_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/clin_doc")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    monkeypatch.delenv("ALLOW_INSECURE_SECRETS", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_production_secrets()


def test_assert_production_secrets_passes_with_real_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/clin_doc")
    monkeypatch.setenv("JWT_SECRET", "a-real-secret")
    monkeypatch.delenv("ALLOW_INSECURE_SECRETS", raising=False)
    assert_production_secrets()  # no raise


def test_assert_production_secrets_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/clin_doc")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    monkeypatch.setenv("ALLOW_INSECURE_SECRETS", "true")
    assert_production_secrets()  # opt-out: no raise


def test_assert_production_secrets_skips_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    # SQLite (dev/demo) is always allowed, even with the default secret.
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./clindoc.db")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    monkeypatch.delenv("ALLOW_INSECURE_SECRETS", raising=False)
    assert_production_secrets()  # no raise


def test_app_uses_cors_allowlist_not_wildcard() -> None:
    """The app's CORS middleware must not use allow_origins=['*'] with credentials."""
    from clin_doc.main import app
    from starlette.middleware.cors import CORSMiddleware

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    origins = cors.kwargs.get("allow_origins")
    assert origins != ["*"]
    assert cors.kwargs.get("allow_credentials") is True
    assert isinstance(origins, list) and len(origins) >= 1


def teardown_module() -> None:  # type: ignore[name-defined]
    # Restore settings cache so other test modules get a fresh Settings.
    get_settings.cache_clear()

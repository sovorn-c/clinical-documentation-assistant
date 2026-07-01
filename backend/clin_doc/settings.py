"""B1 application settings.

Only B1-owned config lives here. The upstream engines read their own env vars
(``LLM_MODEL``/``MODEL``/``API_KEY``/``PHI_HASH_KEY`` etc.) via their own
pydantic-settings — see ``.env.example`` and docs/ARCHITECTURE.md §9.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Clinical Documentation Assistant"
    # Default to a local SQLite file so the app runs without Postgres; prod
    # overrides via DATABASE_URL (postgresql+psycopg://...).
    database_url: str = "sqlite:///./clindoc.db"

    # Auth (Phase 2).
    jwt_secret: str = "change-me-in-production"
    jwt_alg: str = "HS256"
    jwt_ttl_minutes: int = 480

    # CORS (Phase 6 hardening) — comma-separated allowed origins. Defaulted to
    # the local frontend; the demo sets CORS_ORIGINS to its deployed URL. Avoids
    # the insecure allow_origins=["*"] + allow_credentials=True combo.
    cors_origins: str = "http://localhost:3000"

    # Secrets hygiene (Phase 6) — when true, the app refuses to start on a
    # non-SQLite (production) DB if JWT_SECRET is still the default. Set
    # ALLOW_INSECURE_SECRETS=true only for an ephemeral throwaway demo.
    allow_insecure_secrets: bool = False

    # Synthetic-data banner (§11) — always on in the demo.
    synthetic_data_only: bool = True

    # Auth (Phase 2) — a single seeded demo clinician for the demo env.
    seed_username: str = "clinician"
    seed_password: str = "changeme"  # override via env in any real deployment
    seed_display_name: str = "Dr. Demo"

    # Uploaded audio is stored here (gitignored). Phase 5 may swap for object
    # storage; the path recorded on the encounter is what M1 reads.
    upload_dir: str = "uploads"

    # ASR backend (Phase 0 Decision B, executed Phase 5):
    #   mlx_whisper  — local Apple-Silicon dev (M1's default).
    #   faster_whisper — cloud/demo (B1 adapter, cross-platform, CPU).
    asr_backend: str = "mlx_whisper"

    # Rate limiting (Phase 5) — enabled in the demo to keep the public endpoint
    # stable. ``rate_limit_enabled=False`` disables the limiter (e.g. tests).
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 20


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def cors_origin_list() -> list[str]:
    """Parse ``cors_origins`` into a trimmed list (comma-separated)."""
    return [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]


def assert_production_secrets() -> None:
    """Refuse to start on a production DB with the default JWT secret.

    Called from the app lifespan on non-SQLite databases. The demo can opt out
    with ``ALLOW_INSECURE_SECRETS=true`` for an ephemeral deployment.
    """
    s = get_settings()
    if s.database_url.startswith("sqlite"):
        return
    if s.jwt_secret == "change-me-in-production" and not s.allow_insecure_secrets:
        raise RuntimeError(
            "JWT_SECRET is the default on a production database. Set JWT_SECRET "
            "(or ALLOW_INSECURE_SECRETS=true for an ephemeral demo) before starting."
        )

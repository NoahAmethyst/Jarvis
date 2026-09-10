"""Shared, versioned model overrides; provider credentials stay in the environment."""

import os
import re

import psycopg2
from psycopg2.extras import Json

from jarvis.config import POSTGRES_DSN
from jarvis.llm.config import LLMSettings, parse_model_spec
from jarvis.llm.errors import LLMConfigurationError, LLMUnavailableError


class RevisionConflict(Exception):
    pass


def enabled() -> bool:
    return os.getenv("LLM_RUNTIME_CONFIG_ENABLED", "").lower() == "true"


def _connect():
    return psycopg2.connect(
        POSTGRES_DSN, connect_timeout=5, options="-c statement_timeout=5000"
    )


def read_overrides() -> tuple[int, dict[str, str]]:
    try:
        conn = _connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT revision, models FROM llm_runtime_config WHERE id = 1")
                row = cur.fetchone()
                return (row[0], row[1]) if row else (0, {})
        finally:
            conn.close()
    except psycopg2.Error:
        raise LLMUnavailableError("Model configuration storage unavailable") from None


def apply_overrides(settings: LLMSettings, models: dict[str, str]) -> LLMSettings:
    if not isinstance(models, dict) or set(models) - set(settings.profiles):
        raise LLMConfigurationError("Unknown model profile")
    result = settings.model_copy(deep=True)
    for name, spec in models.items():
        if not isinstance(spec, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", spec):
            raise LLMConfigurationError("Invalid model identifier")
        provider_name, _ = parse_model_spec(spec)
        provider = settings.providers.get(provider_name)
        if provider is None:
            raise LLMConfigurationError("Unknown model provider")
        profile = result.profiles[name]
        if profile.tools == "enabled" and not provider.capabilities.tools:
            raise LLMConfigurationError("Profile requires tool support")
        if profile.thinking.mode == "enabled" and not provider.capabilities.thinking:
            raise LLMConfigurationError("Profile requires thinking support")
        profile.model = spec
    return result


def save_overrides(revision: int, models: dict[str, str]) -> int:
    try:
        conn = _connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO llm_runtime_config (id, revision, models)
                    VALUES (1, 0, '{}'::jsonb) ON CONFLICT (id) DO NOTHING
                """)
                cur.execute("""
                    UPDATE llm_runtime_config SET models = %s, revision = revision + 1
                    WHERE id = 1 AND revision = %s RETURNING revision
                """, (Json(models), revision))
                row = cur.fetchone()
                if row is None:
                    raise RevisionConflict
                return row[0]
        finally:
            conn.close()
    except psycopg2.Error:
        raise LLMUnavailableError("Model configuration storage unavailable") from None

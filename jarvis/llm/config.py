from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from jarvis.config import LLM_CONFIG_PATH
from jarvis.llm.errors import LLMConfigurationError, LLMInvalidRequestError


AdapterName = Literal["deepseek", "openai_compatible", "anthropic"]
ThinkingMode = Literal["enabled", "disabled"]
ThinkingFallback = Literal["error", "disable"]
ToolMode = Literal["enabled", "disabled"]

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "llm.yaml"
REQUIRED_PROFILES = frozenset({"answer", "reflection", "agent_dispatch"})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Capabilities(StrictModel):
    tools: bool = False
    thinking: bool = False


class ProviderLimits(StrictModel):
    max_messages: int | None = Field(default=None, ge=1)


class ProviderSettings(StrictModel):
    adapter: AdapterName
    api_key_env: str = Field(min_length=1)
    base_url: str | None = None
    base_url_env: str | None = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
    limits: ProviderLimits = Field(default_factory=ProviderLimits)


class ThinkingSettings(StrictModel):
    mode: ThinkingMode
    effort: Literal["high", "max"] | None = None
    on_unsupported: ThinkingFallback = "error"

    @model_validator(mode="after")
    def validate_effort(self):
        if self.mode == "enabled" and self.effort is None:
            raise ValueError("thinking effort is required when thinking is enabled")
        return self


class RetrySettings(StrictModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    base_delay_seconds: float = Field(default=0.0, ge=0.0, le=10.0)


class ProfileSettings(StrictModel):
    model: str = Field(min_length=1)
    tools: ToolMode
    thinking: ThinkingSettings
    retry: RetrySettings = Field(default_factory=RetrySettings)


class LLMSettings(StrictModel):
    providers: dict[str, ProviderSettings]
    profiles: dict[str, ProfileSettings]

    @model_validator(mode="after")
    def validate_profile_providers(self):
        missing_profiles = REQUIRED_PROFILES.difference(self.profiles)
        if missing_profiles:
            raise ValueError("required LLM profiles are missing")
        for profile_name, profile in self.profiles.items():
            provider_name, _ = parse_model_spec(profile.model)
            if provider_name not in self.providers:
                raise ValueError(
                    f"profile {profile_name!r} references unknown provider {provider_name!r}"
                )
        return self


def parse_model_spec(model_spec: str) -> tuple[str, str]:
    if not isinstance(model_spec, str) or "/" not in model_spec:
        raise LLMInvalidRequestError("invalid LLM model specification")
    provider_name, model_id = (part.strip() for part in model_spec.split("/", 1))
    if not provider_name or not model_id:
        raise LLMInvalidRequestError("invalid LLM model specification")
    return provider_name, model_id


def _default_config_path() -> Path:
    configured = Path(LLM_CONFIG_PATH)
    if LLM_CONFIG_PATH == "llm.yaml":
        return DEFAULT_CONFIG_PATH
    return configured


def load_llm_config(path: str | Path | None = None) -> LLMSettings:
    config_path = Path(path) if path is not None else _default_config_path()
    try:
        with config_path.open(encoding="utf-8") as file:
            data = yaml.safe_load(file)
        if not isinstance(data, dict):
            raise ValueError("LLM configuration root must be a mapping")
        return LLMSettings.model_validate(data)
    except (
        OSError,
        ValueError,
        ValidationError,
        yaml.YAMLError,
        LLMInvalidRequestError,
    ) as error:
        raise LLMConfigurationError("LLM configuration is invalid") from error

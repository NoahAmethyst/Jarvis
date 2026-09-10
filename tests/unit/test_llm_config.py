from pathlib import Path

import pytest
import yaml

from jarvis.llm.config import load_llm_config, parse_model_spec
from jarvis.llm.errors import LLMConfigurationError, LLMInvalidRequestError


ROOT = Path(__file__).resolve().parents[2]


def _write_config(tmp_path: Path, adapter: str = "openai_compatible") -> Path:
    path = tmp_path / "llm.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "test": {
                        "adapter": adapter,
                        "api_key_env": "TEST_API_KEY",
                        "capabilities": {"tools": True, "thinking": False},
                    }
                },
                "profiles": {
                    "answer": {
                        "model": "test/model",
                        "tools": "enabled",
                        "thinking": {"mode": "disabled"},
                    },
                    "reflection": {
                        "model": "test/model",
                        "tools": "disabled",
                        "thinking": {"mode": "disabled"},
                    },
                    "agent_dispatch": {
                        "model": "test/model",
                        "tools": "disabled",
                        "thinking": {"mode": "disabled"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_default_profiles_use_direct_deepseek():
    settings = load_llm_config(ROOT / "llm.yaml")

    answer = settings.profiles["answer"]
    assert answer.model == "deepseek/deepseek-flash"
    assert answer.tools == "enabled"
    assert answer.thinking.mode == "enabled"
    assert answer.thinking.effort == "high"
    assert answer.thinking.on_unsupported == "disable"

    reflection = settings.profiles["reflection"]
    assert reflection.model == "deepseek/deepseek-flash"
    assert reflection.tools == "disabled"
    assert reflection.thinking.mode == "disabled"

    dispatch = settings.profiles["agent_dispatch"]
    assert dispatch.model == "deepseek/deepseek-flash"
    assert dispatch.tools == "disabled"
    assert dispatch.thinking.mode == "disabled"


def test_model_spec_splits_only_first_slash():
    assert parse_model_spec("siliconflow/deepseek-ai/DeepSeek-V4-Pro") == (
        "siliconflow",
        "deepseek-ai/DeepSeek-V4-Pro",
    )


@pytest.mark.parametrize("spec", ["", "deepseek", "/model", "deepseek/"])
def test_invalid_model_spec_is_rejected(spec):
    with pytest.raises(LLMInvalidRequestError, match="invalid LLM model specification"):
        parse_model_spec(spec)


def test_unknown_adapter_name_is_rejected(tmp_path):
    path = _write_config(tmp_path, adapter="some.module.Adapter")

    with pytest.raises(LLMConfigurationError, match="LLM configuration is invalid"):
        load_llm_config(path)


def test_profile_must_reference_configured_provider(tmp_path):
    path = _write_config(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["profiles"]["answer"]["model"] = "missing/model"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(LLMConfigurationError, match="LLM configuration is invalid"):
        load_llm_config(path)


def test_enabled_thinking_requires_effort(tmp_path):
    path = _write_config(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["profiles"]["answer"]["thinking"] = {"mode": "enabled"}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(LLMConfigurationError, match="LLM configuration is invalid"):
        load_llm_config(path)


def test_missing_required_profile_is_configuration_error(tmp_path):
    path = _write_config(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    del data["profiles"]["agent_dispatch"]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(LLMConfigurationError, match="LLM configuration is invalid"):
        load_llm_config(path)


def test_missing_config_file_is_redacted(tmp_path):
    path = tmp_path / "secret-path" / "missing.yaml"

    with pytest.raises(LLMConfigurationError) as exc_info:
        load_llm_config(path)

    assert str(exc_info.value) == "LLM configuration is invalid"
    assert "secret-path" not in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_invalid_yaml_is_redacted(tmp_path):
    path = tmp_path / "llm.yaml"
    path.write_text("providers: [invalid", encoding="utf-8")

    with pytest.raises(LLMConfigurationError) as exc_info:
        load_llm_config(path)

    assert str(exc_info.value) == "LLM configuration is invalid"
    assert "providers" not in str(exc_info.value)


def test_non_mapping_root_is_configuration_error(tmp_path):
    path = tmp_path / "llm.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(LLMConfigurationError, match="LLM configuration is invalid"):
        load_llm_config(path)


def test_unused_provider_key_is_not_required(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    settings = load_llm_config(ROOT / "llm.yaml")

    assert "claude" in settings.providers


def test_siliconflow_chat_limit_is_configured():
    settings = load_llm_config(ROOT / "llm.yaml")

    assert settings.providers["siliconflow"].limits.max_messages == 10

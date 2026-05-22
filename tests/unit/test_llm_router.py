import pytest
from unittest.mock import patch, MagicMock
from jarvis.llm.router import get_model, ProviderNotFoundError, ProviderUnavailableError


def test_get_model_unknown_provider():
    with pytest.raises(ProviderNotFoundError) as exc_info:
        get_model("nonexistent/some-model")
    assert str(exc_info.value) == "provider not exist"


def test_get_model_invalid_format():
    with pytest.raises(ProviderNotFoundError) as exc_info:
        get_model("no-slash-here")
    assert str(exc_info.value) == "provider not exist"


def test_get_model_provider_unavailable():
    with patch("jarvis.llm.router.REGISTRY") as mock_registry:
        mock_provider = MagicMock()
        mock_provider.get_chat_model.side_effect = Exception("connection refused")
        mock_registry.__contains__ = MagicMock(return_value=True)
        mock_registry.__getitem__ = MagicMock(return_value=mock_provider)
        with pytest.raises(ProviderUnavailableError) as exc_info:
            get_model("siliconflow/some-model")
        assert "provider not working:connection refused" in str(exc_info.value)


def test_get_model_siliconflow_returns_chat_model():
    with patch("jarvis.llm.siliconflow.ChatOpenAI") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        result = get_model("siliconflow/deepseek-ai/DeepSeek-V4-Pro")
        mock_cls.assert_called_once()
        assert result is mock_instance


def test_get_model_model_id_with_slash():
    with patch("jarvis.llm.siliconflow.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        get_model("siliconflow/deepseek-ai/DeepSeek-V4-Pro")
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["model"] == "deepseek-ai/DeepSeek-V4-Pro"

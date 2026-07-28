class LLMError(Exception):
    """Base class for safe, public LLM errors."""


class LLMInvalidRequestError(LLMError):
    pass


class LLMConfigurationError(LLMError):
    pass


class LLMCredentialError(LLMConfigurationError):
    pass


class LLMContextLimitError(LLMInvalidRequestError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMUnavailableError(LLMError):
    pass


class LLMInvalidResponseError(LLMError):
    pass

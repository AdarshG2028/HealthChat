"""Service-level errors, mapped to HTTP responses by the API layer."""


class ServiceError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConversationNotFoundError(ServiceError):
    status_code = 404
    code = "CONVERSATION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Conversation not found.")


class ConversationClosedError(ServiceError):
    status_code = 409
    code = "CONVERSATION_CLOSED"

    def __init__(self, status: str) -> None:
        super().__init__(f"This conversation is already {status.lower()}. Start a new one to continue.")


class InvalidOperationError(ServiceError):
    status_code = 409
    code = "INVALID_OPERATION"


class LimitExceededError(ServiceError):
    status_code = 429

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class UpstreamUnavailableError(ServiceError):
    """The LLM failed on a gathering turn. The turn is rolled back; the client may retry."""

    status_code = 503
    retryable = True

    def __init__(
        self, code: str, message: str, retry_after_seconds: float | None = None, *, retryable: bool = True
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.retryable = retryable

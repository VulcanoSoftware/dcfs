from abc import ABCMeta
from http import HTTPStatus

from .base import BusinessError
from .error_code import ErrorCode


class DiscordError(BusinessError, metaclass=ABCMeta):
    pass


class FileSizeTooLarge(DiscordError):
    def __init__(self, size: int):
        message = f"File size {size} exceeds Discord's limit."
        super().__init__(
            message=message,
            code=ErrorCode.FILE_SIZE_TOO_LARGE,
            cause=message,
            http_error=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        )


class MessageNotFound(DiscordError):
    def __init__(self, message_id: int):
        message = f"Message with ID {message_id} not found."
        super().__init__(
            message=message,
            code=ErrorCode.MESSAGE_NOT_FOUND,
            cause=message,
            http_error=HTTPStatus.NOT_FOUND,
        )


class TransientUploadError(DiscordError):
    """Raised when a file upload fails after exhausting retries on transient errors."""

    def __init__(self, file_name: str, retries: int, last_error: Exception):
        message = (
            f"Failed to upload '{file_name}' after {retries} retries: {last_error}"
        )
        super().__init__(
            message=message,
            code=ErrorCode.UNKNOWN,
            cause=str(last_error),
            http_error=HTTPStatus.SERVICE_UNAVAILABLE,
        )

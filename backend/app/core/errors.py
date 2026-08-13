"""Domain-agnostic error model shared across the whole API.

Every error response uses the same envelope so clients can parse failures
uniformly. Feature code raises `AppError` with a machine-readable `code`.
"""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Machine-readable error payload."""

    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    """Uniform error envelope returned on any failed request."""

    error: ErrorDetail


class AppError(Exception):
    """Application-level error that maps to an HTTP error response.

    Usage: `raise AppError(code="campaign.not_found", message="...", status_code=404)`
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        """Convert to the standardized error envelope."""
        return ErrorResponse(
            error=ErrorDetail(code=self.code, message=self.message, details=self.details)
        )

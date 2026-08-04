"""Defines a base AppError class for structured custom errors later.
This prepares us for consistent API error handling."""

class AppError(Exception):
    def __init__(
        self,
        message: str,
        error_code: str = "APP_ERROR",
        status_code: int = 500,
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


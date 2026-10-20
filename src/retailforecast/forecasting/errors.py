"""Actionable forecast failures without exposing native-library or private-path errors."""


class ForecastError(Exception):
    """Carry a stable code/message and HTTP status from domain orchestration to the API."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        """Describe the user's next action without embedding connection strings or paths."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

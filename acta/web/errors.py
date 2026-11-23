"""Domain errors for the Web UI API."""

from __future__ import annotations


class WebError(Exception):
    """Raised for HTTP-mappable Web UI failures."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        fields: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.fields = fields

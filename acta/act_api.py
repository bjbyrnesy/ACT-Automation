from __future__ import annotations

import time

import httpx


class ActClient:
    """Synchronous client for ACT authentication and operation polling."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize an ACT client, optionally with a test transport."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._token: str | None = None
        self._client = httpx.Client(transport=transport)

    def login(self) -> str:
        """Authenticate with ACT and return the bearer token."""
        response = self._client.post(
            f"{self._base_url}/auth/login",
            json={"api_key": self._api_key},
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError("ACT login response did not include a token")
        self._token = token
        return token

    def request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
        params: dict[str, object] | None = None,
    ) -> httpx.Response:
        """Send an authenticated request; the caller inspects the response."""
        if self._token is None:
            raise RuntimeError("ACT login is required before making a request")
        return self._client.request(
            method,
            f"{self._base_url}/{path.lstrip('/')}",
            json=json,
            params=params,
            headers={"Authorization": f"Bearer {self._token}"},
        )

    def poll_operation(
        self,
        operation: dict,
        label: str,
        max_iterations: int = 60,
        interval: float = 10.0,
    ) -> dict:
        """Poll an ACT operation until it completes successfully."""
        result = self.poll_operation_result(operation, label, max_iterations, interval)
        status = result.get("status", "unknown")
        if isinstance(status, str) and status.casefold() == "completed":
            return result
        raise RuntimeError(f"{label} operation completed with status {status}")

    def poll_operation_result(
        self,
        operation: dict,
        label: str,
        max_iterations: int = 60,
        interval: float = 10.0,
    ) -> dict:
        """Poll an ACT operation until finished and return it, whatever its status."""
        operation_id = operation.get("id")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError(f"ACT did not return an operation ID for {label}")
        if self._token is None:
            raise RuntimeError("ACT login is required before polling an operation")
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if interval < 0:
            raise ValueError("interval must not be negative")

        for _ in range(max_iterations):
            time.sleep(interval)
            response = self._client.get(
                f"{self._base_url}/operations/{operation_id}",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise TypeError(f"ACT returned an invalid operation for {label}")
            if result.get("is_completed") is True:
                return result

        iteration_label = "iteration" if max_iterations == 1 else "iterations"
        raise TimeoutError(
            f"{label} did not complete after {max_iterations} {iteration_label}"
        )

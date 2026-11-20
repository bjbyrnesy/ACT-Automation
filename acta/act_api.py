from __future__ import annotations

import time
from typing import Any

import httpx

RUNNING_LAB_STATE = 2


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

    def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            raise RuntimeError(
                "ACT login is required before calling authenticated APIs"
            )
        return {"Authorization": f"Bearer {self._token}"}

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

    def poll_operation(
        self,
        operation: dict,
        label: str,
        max_iterations: int = 60,
        interval: float = 10.0,
    ) -> dict:
        """Poll an ACT operation until it completes successfully."""
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
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise TypeError(f"ACT returned an invalid operation for {label}")
            if result.get("is_completed") is True:
                status = result.get("status", "unknown")
                if isinstance(status, str) and status.casefold() == "completed":
                    return result
                raise RuntimeError(f"{label} operation completed with status {status}")

        iteration_label = "iteration" if max_iterations == 1 else "iterations"
        raise TimeoutError(
            f"{label} did not complete after {max_iterations} {iteration_label}"
        )

    def list_labs(self, user: str, *, page_size: int = 200) -> list[dict[str, Any]]:
        """List labs for ``user`` (``GET /labs?user=&pageSize=``)."""
        response = self._client.get(
            f"{self._base_url}/labs",
            params={"user": user, "pageSize": page_size},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list):
            raise TypeError("ACT returned an invalid labs list")
        return [item for item in result if isinstance(item, dict)]

    def list_running_labs(
        self, user: str, *, page_size: int = 200
    ) -> list[dict[str, Any]]:
        """List labs in Running state (``.state == 2``), matching ``onboard.sh``."""
        return [
            lab
            for lab in self.list_labs(user, page_size=page_size)
            if lab.get("state") == RUNNING_LAB_STATE
        ]

    def get_lab(self, lab_id: str) -> dict[str, Any]:
        """Fetch a single lab by id (``GET /labs/{id}``)."""
        response = self._client.get(
            f"{self._base_url}/labs/{lab_id}",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("ACT returned an invalid lab")
        return payload

    def get_topology_content(self, topology_pathname: str) -> dict[str, Any] | None:
        """Fetch topology JSON content by pathname, or ``None`` if missing."""
        search = self._client.get(
            f"{self._base_url}/topologies",
            params={"topology_pathname": topology_pathname, "pageSize": 1},
            headers=self._auth_headers(),
        )
        search.raise_for_status()
        payload = search.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list) or not result:
            return None
        first = result[0]
        if not isinstance(first, dict):
            return None
        topology_id = first.get("id")
        if not isinstance(topology_id, str) or not topology_id:
            return None

        detail = self._client.get(
            f"{self._base_url}/topologies/{topology_id}",
            headers=self._auth_headers(),
        )
        detail.raise_for_status()
        body = detail.json()
        if not isinstance(body, dict):
            return None
        content = body.get("topology")
        if content is None:
            content = body.get("file")
        if isinstance(content, dict):
            return content
        return None

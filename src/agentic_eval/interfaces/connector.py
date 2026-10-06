"""Connector interface: how the framework talks to an application.

A connector knows transport and session handling (HTTP, WebSocket, SDK call,
message queue, a local process...). It returns the application's *raw*
response untouched; turning that into the common trace is the adapter's job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    """Conversation handle. ``session_id`` is whatever the app uses to keep
    multi-turn context (it may be unknown until after the first turn)."""

    session_id: str | None = None
    test_case_id: str | None = None
    turn_index: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawResponse:
    payload: Any  # parsed body (usually dict) or text
    status_code: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    latency_ms: float | None = None  # filled by the runner if the connector doesn't


class ConnectorError(RuntimeError):
    """The application could not be reached or returned an unusable response."""


class Connector(ABC):
    """Base class for connectors. Construct with ``options`` from the app config."""

    name: str = "connector"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = options or {}

    def open_session(self, test_case_id: str) -> Session:
        """Start a conversation. Default: no server-side session yet."""
        return Session(test_case_id=test_case_id)

    @abstractmethod
    def send(self, session: Session, message: str) -> RawResponse:
        """Send one user message and return the raw response.

        Implementations should update ``session.session_id`` if the response
        carries a conversation id.
        """

    def close_session(self, session: Session) -> None:  # noqa: B027 - optional hook
        """End a conversation (optional)."""

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release resources (optional)."""

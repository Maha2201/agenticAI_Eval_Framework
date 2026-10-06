"""Record and replay connectors.

Recording wraps any real connector and saves each raw response. Replay serves
those saved responses back, so a suite can run offline (CI, adapter
development, metric development) with byte-identical inputs every time.

Layout: ``<dir>/<test_case_id>/turn_<n>.json`` with
``{"request": {"message": ...}, "payload": ..., "status_code": ..., "latency_ms": ...}``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentic_eval.core.registry import register_connector
from agentic_eval.interfaces.connector import Connector, ConnectorError, RawResponse, Session

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _case_dir(root: Path, test_case_id: str) -> Path:
    return root / _SAFE.sub("_", test_case_id)


@register_connector("replay")
class ReplayConnector(Connector):
    """Options: ``dir`` (required), ``check_input`` (default true): fail if the
    scripted user message differs from the one that was recorded."""

    name = "replay"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        if not self.options.get("dir"):
            raise ConnectorError("replay connector needs options.dir")
        self.root = Path(self.options["dir"])
        self.check_input = bool(self.options.get("check_input", True))

    def send(self, session: Session, message: str) -> RawResponse:
        f = _case_dir(self.root, session.test_case_id or "") / f"turn_{session.turn_index}.json"
        if not f.exists():
            raise ConnectorError(f"No recording at {f}. Record it first with --record.")
        data = json.loads(f.read_text(encoding="utf-8"))
        recorded = (data.get("request") or {}).get("message")
        if self.check_input and recorded is not None and recorded != message:
            raise ConnectorError(
                f"Recorded input differs for {f.name}: recorded {recorded!r}, now {message!r}. "
                "Re-record, or set check_input: false."
            )
        return RawResponse(
            payload=data.get("payload"),
            status_code=data.get("status_code"),
            latency_ms=data.get("latency_ms"),
        )


class RecordingConnector(Connector):
    """Wraps a real connector and writes every response to ``dir``."""

    name = "recording"

    def __init__(self, inner: Connector, directory: str | Path) -> None:
        super().__init__({"dir": str(directory)})
        self.inner = inner
        self.root = Path(directory)

    def open_session(self, test_case_id: str) -> Session:
        session = self.inner.open_session(test_case_id)
        d = _case_dir(self.root, test_case_id)
        if d.exists():
            for old in d.glob("turn_*.json"):
                old.unlink()
        return session

    def send(self, session: Session, message: str) -> RawResponse:
        raw = self.inner.send(session, message)
        d = _case_dir(self.root, session.test_case_id or "")
        d.mkdir(parents=True, exist_ok=True)
        record = {
            "request": {"message": message, "session_id": session.session_id},
            "payload": raw.payload,
            "status_code": raw.status_code,
            "latency_ms": raw.latency_ms,
        }
        (d / f"turn_{session.turn_index}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return raw

    def close_session(self, session: Session) -> None:
        self.inner.close_session(session)

    def close(self) -> None:
        self.inner.close()

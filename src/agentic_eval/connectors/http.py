"""Generic HTTP/JSON connector.

Works for any request/response chat API. Everything app-specific is in options:

.. code-block:: yaml

    connector:
      plugin: http
      options:
        base_url: http://127.0.0.1:8000
        path: /chat
        method: POST
        headers: {Authorization: "Bearer ${APP_TOKEN}"}
        body:                         # JSON template
          conversation_id: "{{session_id}}"
          message: "{{message}}"
        session_id_path: conversation_id   # where the response carries the session id
        timeout_s: 60
        verify_ssl: true
        ca_bundle: ${AGENTIC_EVAL_CA_BUNDLE}   # e.g. Zscaler root CA (PEM)
        retries: 0

Placeholders: ``{{message}}``, ``{{session_id}}``, ``{{test_case_id}}``,
``{{turn_index}}``. A value that is only a placeholder keeps its type, so an
unknown session id is sent as JSON ``null`` rather than the string "None".
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from agentic_eval.core.registry import register_connector
from agentic_eval.interfaces.connector import Connector, ConnectorError, RawResponse, Session


def render(template: Any, values: dict[str, Any]) -> Any:
    if isinstance(template, str):
        stripped = template.strip()
        for key, value in values.items():
            if stripped == "{{" + key + "}}":
                return value
        out = template
        for key, value in values.items():
            out = out.replace("{{" + key + "}}", "" if value is None else str(value))
        return out
    if isinstance(template, list):
        return [render(v, values) for v in template]
    if isinstance(template, dict):
        return {k: render(v, values) for k, v in template.items()}
    return template


def dig(payload: Any, dotted: str | None) -> Any:
    if not dotted:
        return None
    current = payload
    for part in dotted.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current


@register_connector("http")
class HttpConnector(Connector):
    name = "http"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        o = self.options
        if not o.get("base_url"):
            raise ConnectorError("http connector needs options.base_url")
        verify: Any = o.get("verify_ssl", True)
        if verify and o.get("ca_bundle"):
            verify = o["ca_bundle"]
        self._client = httpx.Client(
            base_url=str(o["base_url"]).rstrip("/"),
            headers=o.get("headers") or {},
            timeout=float(o.get("timeout_s", 60)),
            verify=verify,
        )
        self._path = o.get("path", "/")
        self._method = str(o.get("method", "POST")).upper()
        self._body = o.get("body", {"message": "{{message}}"})
        self._session_path = o.get("session_id_path")
        self._retries = int(o.get("retries", 0))

    def send(self, session: Session, message: str) -> RawResponse:
        values = {
            "message": message,
            "session_id": session.session_id,
            "test_case_id": session.test_case_id,
            "turn_index": session.turn_index,
        }
        body = render(self._body, values)
        path = render(self._path, values)
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            started = time.perf_counter()
            try:
                if self._method == "GET":
                    resp = self._client.request("GET", path, params=body)
                else:
                    resp = self._client.request(self._method, path, json=body)
                latency = (time.perf_counter() - started) * 1000
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise ConnectorError(f"{self._method} {path} failed: {exc}") from exc
            if resp.status_code >= 500 and attempt < self._retries:
                time.sleep(min(2**attempt, 8))
                continue
            if resp.status_code >= 400:
                raise ConnectorError(
                    f"{self._method} {path} returned {resp.status_code}: {resp.text[:500]}"
                )
            try:
                payload: Any = resp.json()
            except ValueError:
                payload = resp.text
            sid = dig(payload, self._session_path)
            if sid:
                session.session_id = str(sid)
            return RawResponse(
                payload=payload,
                status_code=resp.status_code,
                headers=dict(resp.headers),
                latency_ms=latency,
            )
        raise ConnectorError(f"{self._method} {path} failed: {last_error}")

    def close(self) -> None:
        self._client.close()

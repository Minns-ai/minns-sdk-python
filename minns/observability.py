"""Tier-1 observability ("observed by us") for agents deployed on minns.

The light, framework-agnostic instrumentation tier shared with the minns
control plane. A deployed agent built on this SDK reads the env rails the
deploy injects and emits OTLP GenAI spans (tagged with the agent id), ships
logs, and can request human approvals — with or without the heavy durable
runtime.

This mirrors the agent-forge-sdk ``runtime/`` bridge and the TypeScript
``minns-sdk`` ``observability`` module so the wire contract is identical across
languages.

Env rails injected by the deploy (control plane ``agentDeploy.deploy()``)::

    MINNS_TELEMETRY_URL    OTLP/HTTP trace ingest (forwarded to opto)
    MINNS_LOGS_URL         log shipping endpoint
    MINNS_APPROVAL_URL     human-approval request endpoint
    MINNS_TELEMETRY_TOKEN  per-instance bearer for all three
    MINNS_AGENT_ID         the instance id; tags telemetry as minns.agent.id

Example::

    from minns.observability import init_observability

    obs = init_observability()
    if obs.telemetry:
        obs.telemetry.record_gen_ai(
            system="anthropic", model="claude-opus-4-8",
            input_tokens=120, output_tokens=40,
        )
        obs.telemetry.flush()
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Standardized OTel resource attribute carrying the agent id, so telemetry is
#: attributable with or without the env rails.
AGENT_ID_RESOURCE_ATTR = "minns.agent.id"

AttrValue = str | int | float | bool

_SPAN_KIND_INTERNAL = 1
_SPAN_KIND_CLIENT = 3
_STATUS_OK = 1
_STATUS_ERROR = 2

# Span kinds re-exported for callers building custom spans.
SPAN_KIND_INTERNAL = _SPAN_KIND_INTERNAL
SPAN_KIND_CLIENT = _SPAN_KIND_CLIENT


# ── Env rails ────────────────────────────────────────────────────────────────


@dataclass
class MinnsRails:
    """The env rails the deploy injects. Every field is optional; a missing rail
    simply disables that egress."""

    telemetry_url: str | None = None
    logs_url: str | None = None
    approval_url: str | None = None
    token: str | None = None
    agent_id: str | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def read_minns_env(env: Mapping[str, str] | None = None) -> MinnsRails:
    """Read the minns env rails from ``os.environ`` (or a provided mapping)."""
    source: Mapping[str, str] = os.environ if env is None else env
    return MinnsRails(
        telemetry_url=_clean(source.get("MINNS_TELEMETRY_URL")),
        logs_url=_clean(source.get("MINNS_LOGS_URL")),
        approval_url=_clean(source.get("MINNS_APPROVAL_URL")),
        token=_clean(source.get("MINNS_TELEMETRY_TOKEN")),
        agent_id=_clean(source.get("MINNS_AGENT_ID")),
    )


# ── OTLP/JSON telemetry ──────────────────────────────────────────────────────


def _to_key_value(key: str, value: AttrValue) -> dict[str, Any]:
    # bool is a subclass of int, so check it first.
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": value}}


def _ms_to_nanos(ms: float) -> str:
    return str(int(ms * 1_000_000))


def _bearer(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class TelemetryReporter:
    """Buffers OTLP spans and flushes them to the control plane (OTLP/JSON over
    httpx — no OpenTelemetry SDK dependency). Every span carries the
    ``minns.agent.id`` resource attribute."""

    def __init__(
        self,
        endpoint: str,
        *,
        token: str | None = None,
        agent_id: str | None = None,
        service_name: str | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._token = token
        self._agent_id = agent_id
        self._service_name = service_name or agent_id or "minns-agent"
        # One trace id per reporter; spans share it so they group into a trajectory.
        self._trace_id = secrets.token_hex(16)
        self._buffer: list[dict[str, Any]] = []

    def span(
        self,
        name: str,
        *,
        kind: int = _SPAN_KIND_INTERNAL,
        start_time_ms: float | None = None,
        end_time_ms: float | None = None,
        attributes: dict[str, AttrValue] | None = None,
        error: str | None = None,
    ) -> None:
        """Record a generic span (e.g. a tool call, a unit of work)."""
        start = start_time_ms if start_time_ms is not None else time.time() * 1000
        end = end_time_ms if end_time_ms is not None else start
        status: dict[str, Any] = (
            {"code": _STATUS_ERROR, "message": error} if error else {"code": _STATUS_OK}
        )
        self._buffer.append(
            {
                "traceId": self._trace_id,
                "spanId": secrets.token_hex(8),
                "name": name,
                "kind": kind,
                "startTimeUnixNano": _ms_to_nanos(start),
                "endTimeUnixNano": _ms_to_nanos(end),
                "attributes": [_to_key_value(k, v) for k, v in (attributes or {}).items()],
                "status": status,
            }
        )

    def record_gen_ai(
        self,
        *,
        system: str,
        model: str,
        operation: str = "chat",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        start_time_ms: float | None = None,
        end_time_ms: float | None = None,
        error: str | None = None,
        attributes: dict[str, AttrValue] | None = None,
    ) -> None:
        """Record a GenAI LLM call using OTel GenAI semantic conventions."""
        attrs: dict[str, AttrValue] = {
            "gen_ai.system": system,
            "gen_ai.request.model": model,
            "gen_ai.operation.name": operation,
        }
        if attributes:
            attrs.update(attributes)
        if input_tokens is not None:
            attrs["gen_ai.usage.input_tokens"] = input_tokens
        if output_tokens is not None:
            attrs["gen_ai.usage.output_tokens"] = output_tokens
        self.span(
            f"{operation} {model}",
            kind=_SPAN_KIND_CLIENT,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            attributes=attrs,
            error=error,
        )

    @property
    def empty(self) -> bool:
        """True when nothing is buffered."""
        return not self._buffer

    def flush(self) -> None:
        """Flush buffered spans to the OTLP endpoint. Best-effort; never raises."""
        if not self._buffer:
            return
        spans = self._buffer
        self._buffer = []

        resource_attributes = [_to_key_value("service.name", self._service_name)]
        if self._agent_id:
            resource_attributes.append(_to_key_value(AGENT_ID_RESOURCE_ATTR, self._agent_id))

        payload = {
            "resourceSpans": [
                {
                    "resource": {"attributes": resource_attributes},
                    "scopeSpans": [
                        {"scope": {"name": "minns-sdk", "version": "0"}, "spans": spans}
                    ],
                }
            ]
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(self._endpoint, json=payload, headers=_bearer(self._token))
        except Exception:
            # Telemetry is best-effort: never let an ingest failure break the run.
            pass


def telemetry_from_rails(rails: MinnsRails) -> TelemetryReporter | None:
    """Build a :class:`TelemetryReporter` from the env rails, or ``None``."""
    if not rails.telemetry_url:
        return None
    return TelemetryReporter(rails.telemetry_url, token=rails.token, agent_id=rails.agent_id)


# ── Log shipping ─────────────────────────────────────────────────────────────


class LogShipper:
    """Buffers log lines and POSTs them as ``{"lines": [{"stream", "line"}]}``.
    Flushes on batch-fill or explicit :meth:`flush`; no background timer."""

    def __init__(self, endpoint: str, *, token: str | None = None, batch_size: int = 50) -> None:
        self._endpoint = endpoint
        self._token = token
        self._batch_size = batch_size
        self._buffer: list[dict[str, str]] = []

    def log(self, line: str, stream: str = "stdout") -> None:
        """Queue a line; flushes automatically once the batch fills."""
        self._buffer.append({"stream": stream, "line": line})
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        """Flush buffered lines. Best-effort; never raises."""
        if not self._buffer:
            return
        lines = self._buffer
        self._buffer = []
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(self._endpoint, json={"lines": lines}, headers=_bearer(self._token))
        except Exception:
            pass


def log_shipper_from_rails(rails: MinnsRails) -> LogShipper | None:
    """Build a :class:`LogShipper` from the env rails, or ``None``."""
    if not rails.logs_url:
        return None
    return LogShipper(rails.logs_url, token=rails.token)


# ── Approval requests ────────────────────────────────────────────────────────


def request_approval(
    endpoint: str,
    reason: str,
    detail: str = "",
    *,
    token: str | None = None,
) -> str | None:
    """Request human approval via the control-plane queue.

    Returns the queued approval id (or ``None`` on failure). Fire-and-forget:
    the endpoint enqueues for review and does not block on a human decision —
    pause-and-resume is the job of the durable runtime tier.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                endpoint, json={"reason": reason, "detail": detail}, headers=_bearer(token)
            )
        if response.status_code >= 400:
            return None
        body = response.json()
        approval_id = body.get("approval_id") if isinstance(body, dict) else None
        return approval_id if isinstance(approval_id, str) else None
    except Exception:
        return None


# ── Bootstrap ────────────────────────────────────────────────────────────────


@dataclass
class Observability:
    """The configured tier-1 clients the deploy wired (any may be ``None``)."""

    rails: MinnsRails
    telemetry: TelemetryReporter | None = None
    logs: LogShipper | None = None
    _warnings: list[str] = field(default_factory=list)


def init_observability(env: Mapping[str, str] | None = None) -> Observability:
    """Read the env rails and build the telemetry + log clients the deploy
    wired. Returns the rails plus whichever clients are configured."""
    rails = read_minns_env(env)
    return Observability(
        rails=rails,
        telemetry=telemetry_from_rails(rails),
        logs=log_shipper_from_rails(rails),
    )

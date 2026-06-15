"""Tier-1 observability ("observed by us") for agents deployed on minns.

The light, framework-agnostic instrumentation tier shared with the minns
control plane. A deployed agent built on this SDK reads the env rails the
deploy injects and emits OTLP GenAI spans (tagged with the agent id), ships
logs, and can request human approvals — with or without the heavy durable
runtime.

This mirrors the agent-forge-sdk ``runtime/`` bridge and the TypeScript
``minns-sdk`` ``observability`` module so the wire contract is identical across
languages.

Telemetry is built on the official OpenTelemetry SDK, exported as OTLP/HTTP
**protobuf** (the encoding minns-opto accepts). The OTel packages are an
OPTIONAL dependency, lazy-loaded on first use, so the memory client stays light
for users who don't emit telemetry. Install to enable::

    pip install "minns-sdk[otel]"

Env rails injected by the deploy (control plane ``agentDeploy.deploy()``)::

    MINNS_TELEMETRY_URL    OTLP/HTTP trace ingest (forwarded to opto)
    MINNS_LOGS_URL         log shipping endpoint
    MINNS_APPROVAL_URL     human-approval request endpoint
    MINNS_PROMPT_URL       current (opto-optimized) prompt/model for this agent
    MINNS_TELEMETRY_TOKEN  per-instance bearer for all of the above
    MINNS_AGENT_ID         the instance id; tags telemetry as minns.agent_id
"""

from __future__ import annotations

import contextlib
import importlib
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Standardized OTel resource attribute carrying the agent id. Matches what the
#: minns-opto ingest reads, so spans bucket per agent.
AGENT_ID_RESOURCE_ATTR = "minns.agent_id"

AttrValue = str | int | float | bool


# ── Env rails ────────────────────────────────────────────────────────────────


@dataclass
class MinnsRails:
    """The env rails the deploy injects. Every field is optional; a missing rail
    simply disables that egress."""

    telemetry_url: str | None = None
    logs_url: str | None = None
    approval_url: str | None = None
    prompt_url: str | None = None
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
        prompt_url=_clean(source.get("MINNS_PROMPT_URL")),
        token=_clean(source.get("MINNS_TELEMETRY_TOKEN")),
        agent_id=_clean(source.get("MINNS_AGENT_ID")),
    )


def _bearer(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ── OpenTelemetry trace emission (OTLP protobuf) ─────────────────────────────


def _ms_to_ns(ms: float | None) -> int | None:
    return int(ms * 1_000_000) if ms is not None else None


class TelemetryReporter:
    """Emits OTLP protobuf spans via the official OpenTelemetry SDK. The OTel
    packages are imported lazily; if they are not installed, every method is a
    safe no-op (telemetry is always best-effort). Every span carries the
    ``minns.agent_id`` resource attribute."""

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
        self._provider: Any = None
        self._tracer: Any = None
        self._trace_api: Any = None
        self._init_failed = False
        self._recorded = 0

    def _ensure(self) -> bool:
        """Lazily build the tracer provider. Returns False if OTel is unavailable."""
        if self._tracer is not None:
            return True
        if self._init_failed:
            return False
        try:
            # importlib (not `import`) so the optional OTel packages are not a
            # static/type dependency.
            sdk_trace = importlib.import_module("opentelemetry.sdk.trace")
            sdk_export = importlib.import_module("opentelemetry.sdk.trace.export")
            sdk_resources = importlib.import_module("opentelemetry.sdk.resources")
            otlp = importlib.import_module(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter"
            )
            self._trace_api = importlib.import_module("opentelemetry.trace")

            attributes: dict[str, Any] = {"service.name": self._service_name}
            if self._agent_id:
                attributes[AGENT_ID_RESOURCE_ATTR] = self._agent_id
            resource = sdk_resources.Resource.create(attributes)
            exporter = otlp.OTLPSpanExporter(
                endpoint=self._endpoint,
                headers={"Authorization": f"Bearer {self._token}"} if self._token else None,
            )
            provider = sdk_trace.TracerProvider(resource=resource)
            provider.add_span_processor(sdk_export.BatchSpanProcessor(exporter))
            self._provider = provider
            self._tracer = provider.get_tracer("minns-sdk")
            return True
        except Exception:
            self._init_failed = True
            return False

    def span(
        self,
        name: str,
        *,
        kind: str = "internal",
        start_time_ms: float | None = None,
        end_time_ms: float | None = None,
        attributes: dict[str, AttrValue] | None = None,
        error: str | None = None,
    ) -> None:
        """Record a generic span (e.g. a tool call, a unit of work)."""
        self._recorded += 1
        if not self._ensure():
            return
        # Best-effort: never let telemetry break the run.
        with contextlib.suppress(Exception):
            span_kind = (
                self._trace_api.SpanKind.CLIENT
                if kind == "client"
                else self._trace_api.SpanKind.INTERNAL
            )
            span = self._tracer.start_span(
                name,
                kind=span_kind,
                start_time=_ms_to_ns(start_time_ms),
                attributes=attributes or {},
            )
            if error:
                span.set_status(self._trace_api.Status(self._trace_api.StatusCode.ERROR, error))
            else:
                span.set_status(self._trace_api.Status(self._trace_api.StatusCode.OK))
            span.end(end_time=_ms_to_ns(end_time_ms))

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
            kind="client",
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            attributes=attrs,
            error=error,
        )

    @property
    def empty(self) -> bool:
        """True when no spans have been recorded yet."""
        return self._recorded == 0

    def flush(self) -> None:
        """Flush buffered spans to the OTLP endpoint. Best-effort; never raises."""
        if self._provider is not None:
            with contextlib.suppress(Exception):
                self._provider.force_flush()

    def shutdown(self) -> None:
        """Flush and shut down the exporter (call before the process exits)."""
        if self._provider is not None:
            with contextlib.suppress(Exception):
                self._provider.shutdown()


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
        with contextlib.suppress(Exception), httpx.Client(timeout=10.0) as client:
            client.post(self._endpoint, json={"lines": lines}, headers=_bearer(self._token))


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


# ── Prompt delivery (the "in" half of the optimization loop) ─────────────────


@dataclass
class AgentPromptConfig:
    """The current model config the control plane serves for this agent. The
    agent emits traces; opto optimizes the prompt in batches; the optimized
    prompt is served back here. The agent never optimizes its own prompt."""

    prompt: str
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024
    version: str | None = None
    updated_at: int | None = None


def fetch_agent_prompt(rails: MinnsRails) -> AgentPromptConfig | None:
    """Fetch the agent's current prompt/model from the control plane
    (MINNS_PROMPT_URL), authenticated with the per-instance token. Returns
    ``None`` when not configured or on failure (fall back to built-in defaults).
    """
    if not rails.prompt_url:
        return None
    try:
        headers = {"Authorization": f"Bearer {rails.token}"} if rails.token else {}
        with httpx.Client(timeout=10.0) as client:
            response = client.get(rails.prompt_url, headers=headers)
        if response.status_code >= 400:
            return None
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("prompt"), str):
            return None
        return AgentPromptConfig(
            prompt=body["prompt"],
            model=body.get("model", "") if isinstance(body.get("model"), str) else "",
            temperature=float(body.get("temperature", 0.7)),
            max_tokens=int(body.get("maxTokens", 1024)),
            version=body.get("version"),
            updated_at=body.get("updatedAt"),
        )
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

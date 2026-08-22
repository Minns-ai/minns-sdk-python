"""Fluent EventBuilder for constructing Minns events.

Usage::

    event = (
        client.event("my-agent")
        .action("search", {"q": "test"})
        .outcome({"found": 42})
        .goal("answer user query", priority=4)
        .meta("source", "api")
        .build()
    )
"""

from __future__ import annotations

import asyncio
import inspect
import random
from typing import TYPE_CHECKING, Any, Dict, List, Literal

from ._utils import generate_u128_id, get_nanoseconds, to_u128
from .types import (
    AgentId,
    CognitiveType,
    Event,
    EventContext,
    EventType,
    Goal,
    LearningEvent,
    LocalAck,
    MetadataValue,
    ProcessEventResponse,
    SessionId,
)

if TYPE_CHECKING:
    from .client import AsyncMinnsClient, MinnsClient


class EventBuilder:
    """Fluent builder mirroring the TypeScript ``EventBuilder``.

    The builder is returned by :pymethod:`MinnsClient.event` and
    :pymethod:`AsyncMinnsClient.event`.  Chain method calls to define
    the event, then call :pymethod:`build` (returns a dict), :pymethod:`send`
    (sync), or ``await`` :pymethod:`send_async` (async).
    """

    def __init__(
        self,
        client: MinnsClient | AsyncMinnsClient,
        agent_type: str,
        *,
        agent_id: AgentId | None = None,
        session_id: SessionId | None = None,
        enable_semantic: bool = False,
    ) -> None:
        if agent_id is None:
            raise ValueError("agent_id is required")
        if session_id is None:
            raise ValueError("session_id is required")

        self._client = client
        self._agent_type = agent_type
        self._agent_id = agent_id
        self._session_id = session_id
        self._enable_semantic = enable_semantic

        self._event_payload: EventType | None = None
        self._context_variables: Dict[str, Any] = {}
        self._goals: List[Goal] = []
        self._metadata: Dict[str, MetadataValue] = {}
        self._language: str = "en"
        self._is_code: bool = False
        self._causality: List[str] = []
        self._retry_meta: tuple[int, int] | None = None  # (attempt, max_retries)

    # -- event type setters ---------------------------------------------------

    def action(self, name: str, params: Dict[str, Any] | None = None) -> EventBuilder:
        """Define an Action event."""
        if not name or not name.strip():
            raise ValueError("Action name cannot be empty.")
        self._event_payload = {
            "Action": {
                "action_name": name,
                "parameters": params or {},
                "outcome": {"Success": {"result": "ok"}},
                "duration_ns": 0,
            }
        }
        return self

    def outcome(self, result: Any) -> EventBuilder:
        """Set action outcome to Success. Requires :pymethod:`action` first."""
        self._require_action("outcome")
        self._event_payload["Action"]["outcome"] = {"Success": {"result": result}}  # type: ignore[index]
        return self

    def failure(self, error: str, error_code: int = 0) -> EventBuilder:
        """Set action outcome to Failure. Requires :pymethod:`action` first."""
        self._require_action("failure")
        self._event_payload["Action"]["outcome"] = {  # type: ignore[index]
            "Failure": {"error": error, "error_code": error_code}
        }
        return self

    def partial(self, result: Any, issues: List[str]) -> EventBuilder:
        """Set action outcome to Partial. Requires :pymethod:`action` first."""
        self._require_action("partial")
        self._event_payload["Action"]["outcome"] = {  # type: ignore[index]
            "Partial": {"result": result, "issues": issues}
        }
        return self

    def observation(
        self,
        obs_type: str,
        data: Any = None,
        *,
        confidence: float = 1.0,
        source: str = "environment",
    ) -> EventBuilder:
        """Define an Observation event."""
        if not obs_type or not obs_type.strip():
            raise ValueError("Observation type cannot be empty.")
        self._event_payload = {
            "Observation": {
                "observation_type": obs_type,
                "data": data if data is not None else {},
                "confidence": confidence,
                "source": source,
            }
        }
        return self

    def communication(
        self,
        message_type: str,
        sender: int | str,
        recipient: int | str,
        content: Any = None,
    ) -> EventBuilder:
        """Define a Communication event."""
        if not message_type or not message_type.strip():
            raise ValueError("Communication message_type cannot be empty.")
        self._event_payload = {
            "Communication": {
                "message_type": message_type,
                "sender": int(sender) if isinstance(sender, str) else sender,
                "recipient": int(recipient) if isinstance(recipient, str) else recipient,
                "content": content if content is not None else {},
            }
        }
        return self

    def cognitive(
        self,
        process_type: CognitiveType,
        input_data: Any = None,
        output_data: Any = None,
        reasoning_trace: List[str] | None = None,
    ) -> EventBuilder:
        """Define a Cognitive event."""
        self._event_payload = {
            "Cognitive": {
                "process_type": process_type,
                "input": input_data if input_data is not None else {},
                "output": output_data if output_data is not None else {},
                "reasoning_trace": reasoning_trace or [],
            }
        }
        return self

    def learning(self, learning_event: LearningEvent) -> EventBuilder:
        """Define a Learning event (feedback loop).

        Example::

            builder.learning({"Outcome": {"query_id": "q1", "success": True}})
        """
        self._event_payload = {"Learning": {"event": learning_event}}
        return self

    def context(self, text: str, context_type: str = "general") -> EventBuilder:
        """Define a Context/Text event for claim extraction."""
        if not text or not text.strip():
            raise ValueError("Context text cannot be empty.")
        self._event_payload = {
            "Context": {
                "text": text,
                "context_type": context_type,
                "language": self._language,
            }
        }
        return self

    # -- modifiers ------------------------------------------------------------

    def state(self, variables: Dict[str, Any]) -> EventBuilder:
        """Add environmental state variables."""
        if not isinstance(variables, dict):
            raise TypeError("state() requires a dict.")
        self._context_variables.update(variables)
        return self

    def goal(
        self,
        text: str,
        priority: Literal[1, 2, 3, 4, 5] = 3,
        progress: float = 0.0,
    ) -> EventBuilder:
        """Add an active goal (priority 1-5)."""
        if not text or not text.strip():
            raise ValueError("Goal description cannot be empty.")
        self._goals.append(
            {
                "id": random.randint(0, 999_999),
                "description": text,
                "priority": priority / 5.0,
                "progress": max(0.0, min(1.0, progress)),
                "deadline": None,
                "subgoals": [],
            }
        )
        return self

    def caused_by(self, parent_id: str) -> EventBuilder:
        """Link to a previous event for causality tracking."""
        if not parent_id:
            raise ValueError("caused_by() requires a valid parent_id.")
        self._causality.append(parent_id)
        return self

    def meta(self, key: str, value: str | int | float | bool | Any) -> EventBuilder:
        """Add a metadata key-value pair (auto-wrapped in MetadataValue envelope)."""
        if isinstance(value, str):
            self._metadata[key] = {"String": value}
        elif isinstance(value, bool):
            self._metadata[key] = {"Boolean": value}
        elif isinstance(value, int):
            self._metadata[key] = {"Integer": value}
        elif isinstance(value, float):
            self._metadata[key] = {"Float": value}
        else:
            self._metadata[key] = {"Json": value}
        return self

    def duration(self, ms: int | float) -> EventBuilder:
        """Set action duration in milliseconds. Requires :pymethod:`action` first."""
        self._require_action("duration")
        self._event_payload["Action"]["duration_ns"] = int(ms * 1_000_000)  # type: ignore[index]
        return self

    def semantic(self, enabled: bool = True) -> EventBuilder:
        """Enable/disable semantic indexing for this event."""
        self._enable_semantic = enabled
        return self

    def language(self, lang: str) -> EventBuilder:
        """Set language for Context events (default ``"en"``)."""
        self._language = lang
        if self._event_payload and "Context" in self._event_payload:
            self._event_payload["Context"]["language"] = lang  # type: ignore[index]
        return self

    def is_code(self, enabled: bool = True) -> EventBuilder:
        """Mark this event as containing source code."""
        self._is_code = enabled
        return self

    def retry(self, attempt: int, max_retries: int) -> EventBuilder:
        """Store retry metadata."""
        self._retry_meta = (attempt, max_retries)
        return self

    # -- build ----------------------------------------------------------------

    def build(self) -> Event:
        """Construct and validate the final :class:`Event` dict."""
        if self._event_payload is None:
            raise ValueError("Event payload (action, observation, …) is required.")
        if self._agent_id is None:
            raise ValueError("agent_id is required.")
        if self._session_id is None:
            raise ValueError("session_id is required.")

        metadata = dict(self._metadata)
        if self._retry_meta:
            attempt, max_r = self._retry_meta
            metadata["retry_attempt"] = {"Integer": attempt}
            metadata["retry_max"] = {"Integer": max_r}
            metadata["is_retry"] = {"Boolean": attempt > 0}

        event: Event = {
            "id": generate_u128_id(),
            "timestamp": get_nanoseconds(),
            "agent_id": self._agent_id,
            "session_id": self._session_id,
            "agent_type": self._agent_type,
            "event_type": dict(self._event_payload),
            "causality_chain": [to_u128(c) for c in self._causality],
            "metadata": metadata,
            "context": {
                "environment": {
                    "variables": dict(self._context_variables),
                    "spatial": None,
                    "temporal": {"time_of_day": None, "deadlines": [], "patterns": []},
                },
                "active_goals": [
                    {
                        **g,
                        "id": to_u128(g["id"]),
                        "priority": float(g["priority"]),
                        "progress": float(g["progress"]),
                    }
                    for g in self._goals
                ],
                "resources": {
                    "computational": {
                        "cpu_percent": 0,
                        "memory_bytes": 0,
                        "storage_bytes": 0,
                        "network_bandwidth": 0,
                    },
                    "external": {},
                },
                "embeddings": None,
            },
            "context_size_bytes": 0,
            "segment_pointer": None,
            "is_code": self._is_code,
        }

        # Validate event_type specifics
        et = event["event_type"]
        if "Action" in et:
            a = et["Action"]
            if not a.get("action_name"):
                raise ValueError("Action name is required.")
            if not a.get("outcome"):
                raise ValueError("Action outcome is required.")
            if a.get("duration_ns") is None:
                a["duration_ns"] = 0
        elif "Observation" in et:
            if not et["Observation"].get("observation_type"):
                raise ValueError("Observation type is required.")
        elif "Context" in et:
            if not et["Context"].get("text"):
                raise ValueError("Context text is required.")
        elif "Communication" in et:
            if not et["Communication"].get("message_type"):
                raise ValueError("Communication message_type is required.")
        elif "Cognitive" in et:
            if not et["Cognitive"].get("process_type"):
                raise ValueError("Cognitive process_type is required.")

        return event

    # -- send helpers ---------------------------------------------------------

    def send(self) -> ProcessEventResponse | Any:
        """Build and submit synchronously. Returns the API response.

        If the underlying client is async, this returns a coroutine that
        must be ``await``-ed.
        """
        event = self.build()
        return self._client.process_event(event, enable_semantic=self._enable_semantic)

    async def send_async(self) -> ProcessEventResponse:
        """Build and submit asynchronously."""
        event = self.build()
        return await self._client.process_event(event, enable_semantic=self._enable_semantic)  # type: ignore[misc]

    def enqueue(self) -> LocalAck:
        """Build and fire-and-forget. Returns a local ack immediately.

        With an ASYNC client ``process_event`` returns a coroutine: it is
        scheduled on the running event loop here. Previously the coroutine was
        created and dropped un-awaited, so the event never reached the server
        while this still returned ``success: True`` — a silent data loss. When
        there is no running loop nothing can drive the send, so that is
        reported honestly (``success: False``) instead of acked.
        """
        event = self.build()
        event_id = event.get("id", "queued")
        queued = True
        try:
            result = self._client.process_event(
                event, enable_semantic=self._enable_semantic
            )
            if inspect.isawaitable(result):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop: close the coroutine so it does not warn
                    # about never being awaited, and do not claim it was sent.
                    if hasattr(result, "close"):
                        result.close()
                    queued = False
                else:
                    task = loop.create_task(result)
                    # Retrieve any exception so a failed background send does not
                    # surface as "exception was never retrieved"; the client
                    # reports transport errors through its own telemetry.
                    task.add_done_callback(
                        lambda t: None if t.cancelled() else t.exception()
                    )
        except Exception:
            queued = False
        return {"success": queued, "queued": queued, "event_id": str(event_id)}

    # -- internal -------------------------------------------------------------

    def _require_action(self, method_name: str) -> None:
        if not self._event_payload or "Action" not in self._event_payload:
            raise ValueError(
                f"{method_name}() requires action() to be defined first in the builder chain."
            )

"""Intent specification types and registry.

Mirrors ``intent_registry.ts`` — defines slot specs, extension flags, and
a registry that resolves intent specs by agent type + active goals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence


SlotType = Literal["string", "number", "boolean"]


@dataclass
class SlotSpec:
    """Specification for a single intent slot."""

    optional: bool = False
    enum: tuple[str, ...] | None = None
    free_text: bool = True
    type: SlotType = "string"


@dataclass
class IntentDefinition:
    """A named intent with its slot schema."""

    name: str
    slots: Dict[str, SlotSpec] = field(default_factory=dict)


@dataclass
class ParsedPerception:
    observed_elements: List[str]
    chosen_action: str
    alternatives_considered: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    risk: float = 0.0


@dataclass
class ParsedOutcomeCapture:
    success: bool
    error_code: str | None = None
    observed_result: str | None = None
    expected_result: str | None = None
    recovery_hint: str | None = None


@dataclass
class ExtensionsSpec:
    allow_goal_updates: bool = False
    allow_claims_hint: bool = False
    allow_perception: bool = False
    allow_outcome_capture: bool = False
    allowed_claim_types: tuple[str, ...] | None = None
    max_claims_hint: int = 5
    max_goal_updates: int = 3
    max_perception_elements: int = 20
    max_alternatives: int = 5


@dataclass
class ParsedGoalUpdate:
    goal: str
    progress: float | None = None
    progress_delta: float | None = None
    priority: float | None = None


@dataclass
class ParsedClaimsHint:
    text: str
    type: str | None = None
    confidence: float | None = None


@dataclass
class ParsedSidecarIntent:
    intent: str
    slots: Dict[str, str | int | bool]
    raw_message: str
    enable_semantic: bool = False
    context: str | None = None
    confidence: float | None = None
    goal_updates: List[ParsedGoalUpdate] | None = None
    claims_hint: List[ParsedClaimsHint] | None = None
    perception: ParsedPerception | None = None
    outcome_capture: ParsedOutcomeCapture | None = None


@dataclass
class IntentSpec:
    """Full specification for a domain's intent parsing.

    ``enable_semantic`` is an optional callback that receives the parsed intent
    and returns ``True`` to enable semantic indexing for the resulting event.
    """

    domain: str
    fallback_intent: str
    intents: Sequence[IntentDefinition]
    max_context_chars: int = 800
    extensions: ExtensionsSpec | None = None
    enable_semantic: Callable[[ParsedSidecarIntent], bool] | None = None


class IntentSpecRegistry:
    """Resolve an :class:`IntentSpec` for a given agent type + active goals."""

    def __init__(self) -> None:
        self._specs: Dict[str, IntentSpec] = {}
        self._fallback_by_agent: Dict[str, IntentSpec] = {}

    def register_for_goal(
        self, agent_type: str, goal_description: str, spec: IntentSpec
    ) -> None:
        self._specs[f"{agent_type}::{goal_description}"] = spec

    def register_agent_fallback(self, agent_type: str, spec: IntentSpec) -> None:
        self._fallback_by_agent[agent_type] = spec

    def resolve(
        self,
        agent_type: str,
        active_goals: Sequence[dict[str, Any]] | None = None,
    ) -> IntentSpec | None:
        for g in active_goals or []:
            desc = (g.get("description") or "").strip()
            if not desc:
                continue
            found = self._specs.get(f"{agent_type}::{desc}")
            if found is not None:
                return found
        return self._fallback_by_agent.get(agent_type)

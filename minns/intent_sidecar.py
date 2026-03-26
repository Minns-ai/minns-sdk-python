"""Sidecar instruction builder and LLM-output intent extractor.

Mirrors ``intent_sidecar.ts`` — provides :func:`build_sidecar_instruction`,
:func:`extract_intent_and_response`, and :func:`build_context_snippet`.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from .intent_registry import (
    ExtensionsSpec,
    IntentSpec,
    ParsedClaimsHint,
    ParsedGoalUpdate,
    ParsedOutcomeCapture,
    ParsedPerception,
    ParsedSidecarIntent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_code_fence(s: str) -> str:
    t = s.strip()
    if not t.startswith("```"):
        return t
    first_nl = t.find("\n")
    last_fence = t.rfind("```")
    if first_nl == -1 or last_fence <= first_nl:
        return t
    return t[first_nl + 1 : last_fence].strip()


def _between(s: str, a: str, b: str) -> str | None:
    i = s.find(a)
    if i == -1:
        return None
    j = s.find(b, i + len(a))
    if j == -1:
        return None
    return s[i + len(a) : j].strip()


def _extract_first_json_object(raw: str) -> str | None:
    s = _strip_code_fence(raw)
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _safe_preview(value: Any, max_chars: int) -> str:
    try:
        s = json.dumps(value, default=str)
        return s[:max_chars] + "\u2026" if len(s) > max_chars else s
    except Exception:
        return "[unserializable]"


def _clamp01(x: Any) -> float | None:
    if not isinstance(x, (int, float)):
        return None
    if x != x:  # NaN
        return None
    return max(0.0, min(1.0, float(x)))


def _clamp_minus1_to1(x: Any) -> float | None:
    if not isinstance(x, (int, float)):
        return None
    if x != x:
        return None
    return max(-1.0, min(1.0, float(x)))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_goal_updates(
    payload: Any, spec: IntentSpec
) -> List[ParsedGoalUpdate] | None:
    ex = spec.extensions
    if not ex or not ex.allow_goal_updates:
        return None
    if not isinstance(payload, list):
        return None
    max_n = ex.max_goal_updates
    out: list[ParsedGoalUpdate] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            continue
        gu = ParsedGoalUpdate(goal=goal.strip())
        p = _clamp01(item.get("progress"))
        if p is not None:
            gu.progress = p
        pri = _clamp01(item.get("priority"))
        if pri is not None:
            gu.priority = pri
        pd = _clamp_minus1_to1(item.get("progress_delta"))
        if pd is not None:
            gu.progress_delta = pd
        out.append(gu)
        if len(out) >= max_n:
            break
    return out or None


def _validate_claims_hint(
    payload: Any, spec: IntentSpec
) -> List[ParsedClaimsHint] | None:
    ex = spec.extensions
    if not ex or not ex.allow_claims_hint:
        return None
    if not isinstance(payload, list):
        return None
    max_n = ex.max_claims_hint
    allowed = set(ex.allowed_claim_types) if ex.allowed_claim_types else None
    out: list[ParsedClaimsHint] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        ch = ParsedClaimsHint(text=text.strip())
        t = item.get("type")
        if isinstance(t, str) and t.strip():
            t = t.strip()
            if allowed and t not in allowed:
                continue
            ch.type = t
        conf = _clamp01(item.get("confidence"))
        if conf is not None:
            ch.confidence = conf
        out.append(ch)
        if len(out) >= max_n:
            break
    return out or None


def _validate_perception(
    payload: Any, spec: IntentSpec
) -> ParsedPerception | None:
    ex = spec.extensions
    if not ex or not ex.allow_perception:
        return None
    if not isinstance(payload, dict):
        return None
    raw_elements = payload.get("observed_elements")
    if not isinstance(raw_elements, list) or len(raw_elements) == 0:
        return None
    max_el = ex.max_perception_elements
    elements: list[str] = []
    for el in raw_elements:
        if isinstance(el, str) and el.strip():
            elements.append(el.strip())
        if len(elements) >= max_el:
            break
    if not elements:
        return None
    chosen = payload.get("chosen_action")
    if not isinstance(chosen, str) or not chosen.strip():
        return None
    max_alts = ex.max_alternatives
    alts: list[str] = []
    for alt in payload.get("alternatives_considered") or []:
        if isinstance(alt, str) and alt.strip():
            alts.append(alt.strip())
        if len(alts) >= max_alts:
            break
    assumptions: list[str] = []
    for a in payload.get("assumptions") or []:
        if isinstance(a, str) and a.strip():
            assumptions.append(a.strip())
    risk = _clamp01(payload.get("risk")) or 0.0
    return ParsedPerception(
        observed_elements=elements,
        chosen_action=chosen.strip(),
        alternatives_considered=alts,
        assumptions=assumptions,
        risk=risk,
    )


def _validate_outcome_capture(
    payload: Any, spec: IntentSpec
) -> ParsedOutcomeCapture | None:
    ex = spec.extensions
    if not ex or not ex.allow_outcome_capture:
        return None
    if not isinstance(payload, dict):
        return None
    success = payload.get("success")
    if not isinstance(success, bool):
        return None
    result = ParsedOutcomeCapture(success=success)
    for key in ("error_code", "observed_result", "expected_result", "recovery_hint"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            setattr(result, key, val.strip())
    return result


def _validate_against_spec(
    payload: Any, message: str, spec: IntentSpec
) -> ParsedSidecarIntent | None:
    if not isinstance(payload, dict):
        return None
    intent_name = payload.get("intent")
    if not isinstance(intent_name, str):
        return None
    intent_def = None
    for idef in spec.intents:
        if idef.name == intent_name:
            intent_def = idef
            break
    if intent_def is None:
        return None

    raw_slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    slots: Dict[str, str | int | bool] = {}

    for slot_name, sdef in intent_def.slots.items():
        v = raw_slots.get(slot_name)
        slot_type = sdef.type

        if v is None:
            if not sdef.optional:
                return None
            continue

        if slot_type == "number":
            try:
                num = v if isinstance(v, (int, float)) else float(v)
            except (ValueError, TypeError):
                return None
            slots[slot_name] = num  # type: ignore[assignment]
            continue

        if slot_type == "boolean":
            if isinstance(v, bool):
                slots[slot_name] = v
                continue
            if v == "true":
                slots[slot_name] = True
                continue
            if v == "false":
                slots[slot_name] = False
                continue
            return None

        # string
        if not isinstance(v, str):
            return None
        trimmed = v.strip()
        if not trimmed and not sdef.optional:
            return None
        if sdef.enum:
            if trimmed not in sdef.enum:
                return None
        elif sdef.free_text is False:
            return None
        slots[slot_name] = trimmed

    ctx_val = payload.get("context")
    context = ctx_val.strip() if isinstance(ctx_val, str) and ctx_val.strip() else message

    parsed = ParsedSidecarIntent(
        intent=intent_name,
        slots=slots,
        raw_message=message,
        context=context,
        confidence=_clamp01(payload.get("confidence")),
        goal_updates=_validate_goal_updates(payload.get("goal_updates"), spec),
        claims_hint=_validate_claims_hint(payload.get("claims_hint"), spec),
        perception=_validate_perception(payload.get("perception"), spec),
        outcome_capture=_validate_outcome_capture(payload.get("outcome_capture"), spec),
    )

    parsed.enable_semantic = bool(spec.enable_semantic(parsed)) if spec.enable_semantic else False
    return parsed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_fallback(message: str, spec: IntentSpec) -> ParsedSidecarIntent:
    """Return a fallback intent when parsing fails."""
    return ParsedSidecarIntent(
        intent=spec.fallback_intent,
        slots={},
        raw_message=message,
        context=message,
    )


def build_sidecar_instruction(spec: IntentSpec) -> str:
    """Generate the LLM system instruction for sidecar intent extraction."""
    ex = spec.extensions

    template: Dict[str, Any] = {
        "intent": spec.fallback_intent,
        "slots": {},
        "context": "",
        "confidence": 0.0,
    }
    if ex:
        if ex.allow_goal_updates:
            template["goal_updates"] = []
        if ex.allow_claims_hint:
            template["claims_hint"] = []
        if ex.allow_perception:
            template["perception"] = {}
        if ex.allow_outcome_capture:
            template["outcome_capture"] = {}

    lines: list[str] = [
        "Output exactly two blocks, nothing else.",
        "BEGIN_INTENT_JSON",
        json.dumps(template),
        "END_INTENT_JSON",
        "BEGIN_ASSISTANT_RESPONSE",
        "(normal response)",
        "END_ASSISTANT_RESPONSE",
        f"Domain: {spec.domain}",
        "Valid intents:",
    ]

    for idef in spec.intents:
        if not idef.slots:
            lines.append(f"- {idef.name}")
            continue
        parts: list[str] = []
        for sn, sd in idef.slots.items():
            req = "?" if sd.optional else "!"
            type_label = sd.type
            if sd.enum:
                parts.append(f"{sn}{req}={'|'.join(sd.enum)}")
            else:
                parts.append(f"{sn}{req}={type_label}")
        lines.append(f"- {idef.name}: {', '.join(parts)}")

    if ex:
        if ex.allow_goal_updates:
            lines.append(
                f"goal_updates: optional array of {{goal, progress(0..1)?, "
                f"progress_delta(-1..1)?, priority(0..1)?}}. max {ex.max_goal_updates}."
            )
        if ex.allow_claims_hint:
            lines.append(
                f"claims_hint: optional array of {{text, type?, confidence(0..1)?}}. "
                f"max {ex.max_claims_hint}."
            )
            if ex.allowed_claim_types:
                lines.append(
                    f"If type provided, must be one of: {'|'.join(ex.allowed_claim_types)}"
                )
        if ex.allow_perception:
            lines.append(
                f"perception: optional {{observed_elements: string[] (min 1, "
                f"max {ex.max_perception_elements}), chosen_action: string (required), "
                f"alternatives_considered: string[] (max {ex.max_alternatives}), "
                f"assumptions: string[], risk: number (0..1)}}."
            )
        if ex.allow_outcome_capture:
            lines.append(
                "outcome_capture: optional {success: boolean (required), "
                "error_code?: string, observed_result?: string, "
                "expected_result?: string, recovery_hint?: string}."
            )

    lines.append(
        f'Rules: JSON only inside intent block. If unsure use intent="{spec.fallback_intent}".'
    )
    return "\n".join(lines)


def build_context_snippet(context: Any, spec: IntentSpec) -> str:
    """Truncate context to fit within the spec's ``max_context_chars``."""
    cap = spec.max_context_chars
    return _safe_preview(context, cap)


def extract_intent_and_response(
    model_text: str,
    user_message: str,
    spec: IntentSpec,
    *,
    on_telemetry: Callable[[Dict[str, Any]], None] | None = None,
) -> tuple[ParsedSidecarIntent, str]:
    """Parse LLM output into a structured intent and assistant response.

    Returns ``(intent, assistant_response)``.
    """
    start = time.monotonic()
    cleaned = _strip_code_fence(model_text)

    intent_chunk = _between(cleaned, "BEGIN_INTENT_JSON", "END_INTENT_JSON")
    response_chunk = _between(cleaned, "BEGIN_ASSISTANT_RESPONSE", "END_ASSISTANT_RESPONSE")

    intent: ParsedSidecarIntent | None = None

    if intent_chunk:
        try:
            intent = _validate_against_spec(json.loads(intent_chunk), user_message, spec)
        except (json.JSONDecodeError, Exception):
            pass

    if intent is None:
        candidate = _extract_first_json_object(intent_chunk or cleaned)
        if candidate:
            try:
                intent = _validate_against_spec(json.loads(candidate), user_message, spec)
            except (json.JSONDecodeError, Exception):
                pass

    result_intent = intent or build_fallback(user_message, spec)
    result_response = response_chunk or cleaned

    if on_telemetry is not None:
        on_telemetry(
            {
                "type": "intent_parse",
                "duration_ms": (time.monotonic() - start) * 1000,
                "intent": result_intent.intent,
                "is_fallback": intent is None,
                "token_count": len(model_text) // 4,
                "metadata": {
                    "has_intent_chunk": intent_chunk is not None,
                    "has_response_chunk": response_chunk is not None,
                    "raw_length": len(model_text),
                },
            }
        )

    return result_intent, result_response

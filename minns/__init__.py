"""Minns SDK — Python client for the graph-native memory engine.

Quickstart::

    from minns import MinnsClient, create_client

    # Synchronous
    client = create_client("sk-...", agent_id=1, session_id=42)
    health = client.health_check()
    result = client.query("What are Alice's connections?")

    # Fluent event builder
    client.event("my-agent").action("search", {"q": "test"}).send()

    # Async
    from minns import AsyncMinnsClient, create_async_client

    async with AsyncMinnsClient(api_key="sk-...") as client:
        result = await client.query("What happened yesterday?")
"""

from .builder import EventBuilder
from .client import (
    AsyncMinnsClient,
    MinnsClient,
    create_async_client,
    create_client,
)
from .errors import MinnsError
from .intent_registry import (
    ExtensionsSpec,
    IntentDefinition,
    IntentSpec,
    IntentSpecRegistry,
    ParsedClaimsHint,
    ParsedGoalUpdate,
    ParsedOutcomeCapture,
    ParsedPerception,
    ParsedSidecarIntent,
    SlotSpec,
)
from .intent_sidecar import (
    build_context_snippet,
    build_fallback,
    build_sidecar_instruction,
    extract_intent_and_response,
)
from .observability import (
    AGENT_ID_RESOURCE_ATTR,
    AgentPromptConfig,
    LogShipper,
    MinnsRails,
    Observability,
    TelemetryReporter,
    fetch_agent_prompt,
    init_observability,
    log_shipper_from_rails,
    read_minns_env,
    request_approval,
    telemetry_from_rails,
)
from .types import (
    # Scalar aliases
    UInt64,
    UInt128,
    AgentId,
    ContextHash,
    EventId,
    SessionId,
    GoalId,
    # Enums
    CognitiveType,
    SearchMode,
    FusionStrategy,
    # Core types
    Event,
    EventType,
    EventContext,
    ActionOutcome,
    MetadataValue,
    LearningEvent,
    # Request / response types
    ProcessEventResponse,
    SimpleEventRequest,
    StateChangeEventRequest,
    TransactionEventRequest,
    ConversationIngestRequest,
    ConversationIngestResponse,
    MessageRequest,
    MessageResponse,
    NLQRequest,
    NLQResponse,
    SearchRequest,
    SearchResponse,
    ClaimSearchRequest,
    ClaimSearchResponse,
    MemoryResponse,
    StrategyResponse,
    EpisodeResponse,
    HealthResponse,
    StatsResponse,
    GraphResponse,
    GraphImportRequest,
    GraphImportResponse,
    AnalyticsResponse,
    MinnsQLResponse,
    CodeFileEventRequest,
    CodeReviewEventRequest,
    CodeSearchRequest,
    CodeSearchResponse,
    StructuredMemoryTemplate,
    StructuredMemoryUpsertRequest,
    LedgerAppendRequest,
    StateTransitionRequest,
    PreferenceUpdateRequest,
    TreeAddChildRequest,
    TableCreateRequest,
    TableSchema,
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    AgentRegisterRequest,
    ModuleUploadRequest,
    LocalAck,
    TelemetryData,
    RecallContextResult,
    PerceiveActLearnResult,
)

__all__ = [
    # Client
    "MinnsClient",
    "AsyncMinnsClient",
    "create_client",
    "create_async_client",
    "EventBuilder",
    "MinnsError",
    # Intent parsing
    "IntentSpec",
    "IntentSpecRegistry",
    "IntentDefinition",
    "SlotSpec",
    "ExtensionsSpec",
    "ParsedSidecarIntent",
    "ParsedGoalUpdate",
    "ParsedClaimsHint",
    "ParsedPerception",
    "ParsedOutcomeCapture",
    "build_sidecar_instruction",
    "extract_intent_and_response",
    "build_context_snippet",
    "build_fallback",
    # Observability (tier-1: "observed by us")
    "AGENT_ID_RESOURCE_ATTR",
    "MinnsRails",
    "read_minns_env",
    "TelemetryReporter",
    "telemetry_from_rails",
    "LogShipper",
    "log_shipper_from_rails",
    "request_approval",
    "AgentPromptConfig",
    "fetch_agent_prompt",
    "Observability",
    "init_observability",
]

__version__ = "0.8.3"

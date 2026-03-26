"""Type definitions for the Minns SDK.

All types use :class:`~typing.TypedDict` to maintain direct JSON wire-format
compatibility with the MinnsDB API.  Tagged unions (``EventType``,
``ActionOutcome``, …) are represented as plain dicts matching the Rust
``serde`` serialisation format.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

from typing_extensions import NotRequired, TypedDict

# ============================================================================
# Scalar aliases
# ============================================================================

UInt64 = Union[int, str]
"""Server-side u64 — accepts ``int`` or stringified ``int``."""

UInt128 = str
"""Server-side u128 — always a stringified integer."""

AgentId = UInt64
ContextHash = UInt64
EventId = UInt128
SessionId = UInt64
GoalId = UInt64

# ============================================================================
# Enum-like literals
# ============================================================================

CognitiveType = Literal[
    "GoalFormation", "Planning", "Reasoning", "MemoryRetrieval", "LearningUpdate"
]

SearchMode = Literal["keyword", "semantic", "hybrid"]
FusionStrategy = Literal["RRF", "Linear", "Max"]
StructuredMemoryProvenance = Literal["Manual", "EpisodePipeline", "NlqUpsert"]
CodeSearchKind = Literal[
    "function", "class", "enum", "interface", "module", "variable", "typealias"
]
CodeReviewAction = Literal["comment", "approve", "request_changes"]
WorkflowOutcome = Literal["success", "partial", "failure"]
LedgerDirection = Literal["Credit", "Debit"]
MemoryTier = Literal["Episodic", "Semantic", "Schema"]
ConsolidationStatus = Literal["Active", "Consolidated", "Archived"]
MessageRole = Literal["user", "assistant"]
ImportMode = Literal["replace", "merge"]
ColumnType = Literal["String", "Int64", "Float64", "Bool", "Timestamp", "Json", "NodeRef"]
TemporalWhen = Literal["active", "all"]

# ============================================================================
# Tagged unions — plain dicts matching Rust serde wire format
# ============================================================================

EventType = Dict[str, Any]
"""Exactly one key: ``Action``, ``Observation``, ``Cognitive``,
``Communication``, ``Learning``, or ``Context``."""

ActionOutcome = Dict[str, Any]
"""``{"Success": {"result": ...}}``, ``{"Failure": {"error": ..., "error_code": ...}}``,
or ``{"Partial": {"result": ..., "issues": [...]}}``."""

MetadataValue = Dict[str, Any]
"""``{"String": str}``, ``{"Integer": int}``, ``{"Float": float}``,
``{"Boolean": bool}``, or ``{"Json": Any}``."""

LearningEvent = Dict[str, Any]
"""One of ``MemoryRetrieved``, ``MemoryUsed``, ``StrategyServed``,
``StrategyUsed``, ``Outcome``, ``ClaimRetrieved``, ``ClaimUsed``."""

StructuredMemoryTemplate = Dict[str, Any]
"""``{"Ledger": ...}``, ``{"StateMachine": ...}``, ``{"PreferenceList": ...}``,
or ``{"Tree": ...}``."""

TableConstraint = Dict[str, List[str]]
"""``{"PrimaryKey": [...]}``, ``{"Unique": [...]}``, or ``{"NotNull": [...]}``."""

# ============================================================================
# Event sub-types
# ============================================================================


class ActionEvent(TypedDict):
    action_name: str
    parameters: Any
    outcome: ActionOutcome
    duration_ns: NotRequired[int]


class ObservationEvent(TypedDict):
    observation_type: str
    data: Any
    confidence: float
    source: str


class CognitiveEvent(TypedDict):
    process_type: CognitiveType
    input: Any
    output: Any
    reasoning_trace: List[str]


class CommunicationEvent(TypedDict):
    message_type: str
    sender: AgentId
    recipient: AgentId
    content: Any


class ContextEvent(TypedDict):
    text: str
    context_type: str
    language: NotRequired[str]


# ============================================================================
# Context hierarchy
# ============================================================================


class BoundingBox(TypedDict):
    min: Tuple[float, float, float]
    max: Tuple[float, float, float]


class SpatialContext(TypedDict):
    location: Tuple[float, float, float]
    bounds: Optional[BoundingBox]
    reference_frame: str


class TimeOfDay(TypedDict):
    hour: int
    minute: int
    timezone: str


class Deadline(TypedDict):
    goal_id: UInt64
    timestamp: int
    priority: int


class TemporalPattern(TypedDict):
    pattern_name: str
    frequency: int
    phase: int


class TemporalContext(TypedDict):
    time_of_day: Optional[TimeOfDay]
    deadlines: List[Deadline]
    patterns: List[TemporalPattern]


class EnvironmentState(TypedDict):
    variables: Dict[str, Any]
    spatial: Optional[SpatialContext]
    temporal: TemporalContext


class Goal(TypedDict):
    id: UInt64
    description: str
    priority: float
    deadline: Optional[int]
    progress: float
    subgoals: List[UInt64]


class ComputationalResources(TypedDict):
    cpu_percent: float
    memory_bytes: int
    storage_bytes: int
    network_bandwidth: float


class ResourceAvailability(TypedDict):
    available: bool
    capacity: float
    current_usage: float
    estimated_cost: NotRequired[Optional[float]]


class ResourceState(TypedDict):
    computational: ComputationalResources
    external: Dict[str, ResourceAvailability]


class EventContext(TypedDict):
    environment: EnvironmentState
    active_goals: List[Goal]
    resources: ResourceState
    fingerprint: NotRequired[ContextHash]
    goal_bucket_id: NotRequired[int]
    embeddings: Optional[List[float]]


# ============================================================================
# Core event
# ============================================================================


class Event(TypedDict):
    id: NotRequired[EventId]
    timestamp: NotRequired[Union[int, str]]
    agent_id: AgentId
    agent_type: str
    session_id: SessionId
    event_type: EventType
    causality_chain: List[EventId]
    context: EventContext
    metadata: Dict[str, MetadataValue]
    context_size_bytes: int
    segment_pointer: Optional[str]
    is_code: NotRequired[bool]


# ============================================================================
# Request / response types
# ============================================================================


class ProcessEventResponse(TypedDict):
    success: bool
    nodes_created: int
    patterns_detected: int
    processing_time_ms: float
    event_id: NotRequired[str]
    claims_extracted: NotRequired[int]


class ErrorResponse(TypedDict):
    error: str
    details: NotRequired[str]


# -- Claims ------------------------------------------------------------------


class EvidenceSpan(TypedDict):
    start_offset: int
    end_offset: int
    text_snippet: str


class ClaimEntity(TypedDict):
    text: str
    label: str


class ClaimResponse(TypedDict):
    claim_id: UInt64
    claim_text: str
    confidence: float
    source_event_id: UInt64
    similarity: Optional[float]
    evidence_spans: List[EvidenceSpan]
    support_count: int
    status: str
    created_at: Union[int, str]
    last_accessed: Union[int, str]
    claim_type: str
    subject_entity: Optional[str]
    expires_at: Optional[Union[int, str]]
    temporal_weight: float
    superseded_by: Optional[UInt64]
    entities: List[ClaimEntity]


class ClaimSearchRequest(TypedDict):
    query_text: str
    top_k: NotRequired[int]
    min_similarity: NotRequired[float]


class ClaimSearchGroup(TypedDict):
    subject: str
    claims: List[ClaimResponse]


class ClaimSearchResponse(TypedDict):
    groups: List[ClaimSearchGroup]
    ungrouped: List[ClaimResponse]
    total_results: int


# -- Memories -----------------------------------------------------------------


class MemoryResponse(TypedDict):
    id: UInt64
    agent_id: AgentId
    session_id: SessionId
    summary: str
    takeaway: str
    causal_note: str
    tier: MemoryTier
    consolidation_status: ConsolidationStatus
    schema_id: NotRequired[UInt64]
    consolidated_from: NotRequired[List[UInt64]]
    strength: float
    relevance_score: float
    access_count: int
    formed_at: Union[int, str]
    last_accessed: Union[int, str]
    context_hash: ContextHash
    context: EventContext
    outcome: str
    memory_type: str


class ContextMemoriesRequest(TypedDict):
    context: EventContext
    limit: NotRequired[int]
    min_similarity: NotRequired[float]
    agent_id: NotRequired[AgentId]
    session_id: NotRequired[SessionId]


# -- Strategies ---------------------------------------------------------------


class PlaybookBranch(TypedDict):
    condition: str
    action: str


class PlaybookStep(TypedDict):
    step: int
    action: str
    condition: str
    skip_if: str
    recovery: str
    branches: List[PlaybookBranch]


class ReasoningStepResponse(TypedDict):
    description: str
    applicability: NotRequired[str]
    expected_outcome: NotRequired[str]
    sequence_order: int


class StrategyResponse(TypedDict):
    id: int
    name: str
    agent_id: AgentId
    summary: str
    when_to_use: str
    when_not_to_use: str
    failure_modes: List[str]
    playbook: List[PlaybookStep]
    counterfactual: str
    supersedes: List[UInt64]
    applicable_domains: List[str]
    quality_score: float
    success_count: int
    failure_count: int
    reasoning_steps: List[ReasoningStepResponse]
    strategy_type: str
    support_count: int
    expected_success: float
    expected_cost: float
    expected_value: float
    confidence: float
    goal_bucket_id: int
    behavior_signature: str
    precondition: str
    action_hint: str


class SimilarStrategyResponse(StrategyResponse):
    score: float


class StrategySimilarityRequest(TypedDict):
    goal_ids: NotRequired[List[UInt64]]
    tool_names: NotRequired[List[str]]
    result_types: NotRequired[List[str]]
    context_hash: NotRequired[ContextHash]
    agent_id: NotRequired[AgentId]
    limit: NotRequired[int]
    min_score: NotRequired[float]


class ActionSuggestionResponse(TypedDict):
    action_name: str
    success_probability: float
    evidence_count: int
    reasoning: str


# -- Episodes -----------------------------------------------------------------


class EpisodeResponse(TypedDict):
    id: UInt64
    agent_id: AgentId
    event_count: int
    significance: float
    outcome: Optional[str]


# -- Stats --------------------------------------------------------------------


class _MemoryStats(TypedDict):
    total: int
    avg_strength: float
    avg_access_count: float
    agents_with_memories: int


class _StrategyStats(TypedDict):
    total: int
    high_quality: int
    avg_quality: float
    agents_with_strategies: int


class _ClaimStats(TypedDict):
    total: int
    embeddings_indexed: int


class _GraphStats(TypedDict):
    nodes: int
    edges: int
    avg_degree: float
    largest_component: int


class _Stores(TypedDict):
    memories: _MemoryStats
    strategies: _StrategyStats
    claims: _ClaimStats
    graph: _GraphStats


class StatsResponse(TypedDict):
    total_events_processed: int
    total_nodes_created: int
    total_episodes_detected: int
    total_memories_formed: int
    total_strategies_extracted: int
    total_reinforcements_applied: int
    average_processing_time_ms: float
    stores: _Stores


# -- Graph --------------------------------------------------------------------


class GraphNodeResponse(TypedDict):
    id: int
    label: str
    node_type: str
    created_at: int
    properties: Dict[str, Any]


class GraphEdgeResponse(TypedDict):
    id: int
    source: int  # 'from' in TS; renamed to avoid Python keyword
    target: int  # 'to' in TS
    edge_type: str
    weight: float
    confidence: float


class GraphResponse(TypedDict):
    nodes: List[GraphNodeResponse]
    edges: List[GraphEdgeResponse]


class GraphQuery(TypedDict, total=False):
    limit: int
    session_id: SessionId
    agent_type: str


class GraphContextQuery(TypedDict):
    context_hash: ContextHash
    limit: NotRequired[int]
    session_id: NotRequired[SessionId]
    agent_type: NotRequired[str]


class GraphQueryFilter(TypedDict):
    key: str
    value: Union[str, int, bool]
    operator: NotRequired[Literal["equals", "contains", "starts_with", "ends_with"]]


class GraphNodeQueryRequest(TypedDict):
    node_types: List[str]
    property_filters: List[GraphQueryFilter]


class GraphNodeQueryResult(TypedDict):
    id: Union[str, int]
    node_type: NotRequired[str]
    properties: NotRequired[Dict[str, Any]]


class GraphNodeQueryResponse(TypedDict):
    results: List[GraphNodeQueryResult]


class GraphTraverseQuery(TypedDict):
    start: str
    max_depth: NotRequired[int]
    node_types: NotRequired[List[str]]


class GraphTraverseResponse(TypedDict):
    nodes: List[GraphNodeQueryResult]
    edges: List[GraphEdgeResponse]


class GraphPersistResponse(TypedDict):
    success: bool
    nodes_persisted: int
    edges_persisted: int


class GraphImportNode(TypedDict):
    name: str
    type: NotRequired[str]
    properties: NotRequired[Dict[str, Any]]


class GraphImportEdge(TypedDict):
    source: str
    target: str
    type: NotRequired[str]
    label: NotRequired[str]
    weight: NotRequired[float]
    confidence: NotRequired[float]
    valid_from: NotRequired[int]
    valid_until: NotRequired[int]
    properties: NotRequired[Dict[str, Any]]


class GraphImportRequest(TypedDict):
    nodes: List[GraphImportNode]
    edges: List[GraphImportEdge]
    group_id: NotRequired[str]


class GraphImportResponse(TypedDict):
    nodes_created: int
    nodes_reused: int
    edges_created: int
    errors: List[str]


# -- Analytics ----------------------------------------------------------------


class LearningMetricsResponse(TypedDict):
    total_events: int
    unique_contexts: int
    learned_patterns: int
    strong_memories: int
    overall_success_rate: float
    average_edge_weight: float


class AnalyticsResponse(TypedDict):
    node_count: int
    edge_count: int
    connected_components: int
    largest_component_size: int
    average_path_length: float
    diameter: int
    clustering_coefficient: float
    average_clustering: float
    modularity: float
    community_count: int
    learning_metrics: LearningMetricsResponse


class CommunityInfo(TypedDict):
    community_id: int
    size: int
    node_ids: List[int]


class CommunityDetectionResponse(TypedDict):
    communities: List[CommunityInfo]
    modularity: float
    iterations: int
    community_count: int
    algorithm: str


class CentralityScore(TypedDict):
    node_id: int
    degree: float
    betweenness: float
    closeness: float
    eigenvector: float
    pagerank: float
    combined: float


CentralityResponse = List[CentralityScore]


class PPRScore(TypedDict):
    node_id: int
    score: float


class PPRResponse(TypedDict):
    source_node_id: int
    algorithm: str
    scores: List[PPRScore]


class ReachableNode(TypedDict):
    node_id: int
    origin: int
    arrival_time: Union[int, str]
    hops: int
    predecessor: int


class ReachabilityResponse(TypedDict):
    source_node_id: int
    reachable_count: int
    max_depth: int
    edges_traversed: int
    reachable: List[ReachableNode]


class CausalPathResponse(TypedDict):
    source: int
    target: int
    found: bool
    path: List[int]


class IndexStatsResponse(TypedDict):
    insert_count: int
    query_count: int
    range_query_count: int
    hit_count: int
    miss_count: int
    last_accessed: Union[int, str]


# -- Health -------------------------------------------------------------------


class WriteLane(TypedDict):
    lane_id: int
    depth: int
    in_flight: int
    completed: int
    rejected: int


class WriteLanes(TypedDict):
    num_lanes: int
    lanes: List[WriteLane]
    total_submitted: int
    total_completed: int
    total_rejected: int
    write_p50_ms: float
    write_p95_ms: float
    write_p99_ms: float


class ReadGate(TypedDict):
    permits_total: int
    in_flight: int
    completed: int
    rejected: int
    read_p50_ms: float
    read_p95_ms: float
    read_p99_ms: float


class SequenceTracker(TypedDict):
    tracked_domains: int


class HealthResponse(TypedDict):
    status: str
    version: str
    uptime_seconds: float
    is_healthy: bool
    node_count: int
    edge_count: int
    processing_rate: float
    write_lanes: WriteLanes
    read_gate: ReadGate
    sequence_tracker: SequenceTracker


# -- Search -------------------------------------------------------------------


class SearchRequest(TypedDict):
    query: str
    mode: SearchMode
    limit: NotRequired[int]
    fusion_strategy: NotRequired[FusionStrategy]


class SearchResult(TypedDict):
    node_id: int
    score: float
    node_type: str
    properties: Dict[str, Any]


class SearchResponse(TypedDict):
    results: List[SearchResult]
    mode: SearchMode
    total: int


# -- NLQ ----------------------------------------------------------------------


class NLQRequest(TypedDict):
    question: str
    group_id: NotRequired[str]
    limit: NotRequired[int]
    offset: NotRequired[int]
    session_id: NotRequired[int]
    include_context: NotRequired[bool]
    metadata: NotRequired[Dict[str, Any]]


class NLQEntityResolved(TypedDict):
    text: str
    node_id: int
    node_type: str
    confidence: float


class NLQResponse(TypedDict):
    answer: str
    intent: str
    entities_resolved: List[NLQEntityResolved]
    confidence: float
    result_count: int
    execution_time_ms: float
    query_used: str
    explanation: List[str]
    total_count: int


# -- Simple Event -------------------------------------------------------------


class SimpleEventRequest(TypedDict):
    agent_id: AgentId
    agent_type: str
    session_id: SessionId
    action: str
    data: Dict[str, Any]
    success: bool
    enable_semantic: NotRequired[bool]


# -- State Change & Transaction Events ----------------------------------------


class StateChangeEventRequest(TypedDict):
    agent_id: AgentId
    agent_type: str
    session_id: SessionId
    entity: str
    new_state: str
    old_state: NotRequired[str]
    trigger: NotRequired[str]
    extra_metadata: NotRequired[Dict[str, Any]]
    enable_semantic: NotRequired[bool]


class TransactionEventRequest(TypedDict):
    agent_id: AgentId
    agent_type: str
    session_id: SessionId
    from_entity: str  # 'from' in TS — renamed to avoid Python keyword
    to_entity: str  # 'to' in TS
    amount: float
    direction: NotRequired[LedgerDirection]
    description: NotRequired[str]
    extra_metadata: NotRequired[Dict[str, Any]]
    enable_semantic: NotRequired[bool]


# -- Conversation Ingestion ---------------------------------------------------


class ConversationMessage(TypedDict):
    role: MessageRole
    content: str
    metadata: NotRequired[Dict[str, Any]]


class ConversationSession(TypedDict):
    session_id: str
    topic: NotRequired[str]
    messages: List[ConversationMessage]
    contains_fact: NotRequired[bool]
    fact_id: NotRequired[Optional[str]]
    fact_quote: NotRequired[Optional[str]]


class ConversationIngestRequest(TypedDict):
    case_id: NotRequired[str]
    sessions: List[ConversationSession]
    include_assistant_facts: NotRequired[bool]
    group_id: NotRequired[str]
    metadata: NotRequired[Dict[str, Any]]


class ConversationCompactionResult(TypedDict):
    facts_extracted: int
    goals_extracted: int
    goals_deduplicated: int
    procedural_steps: int
    memories_created: int
    memories_updated: int
    memories_deleted: int
    playbooks_extracted: int
    llm_success: bool


class ConversationIngestResponse(TypedDict):
    case_id: str
    messages_processed: int
    events_submitted: int
    compaction: ConversationCompactionResult
    rolling_summary_started: bool


# -- Single Message -----------------------------------------------------------


class MessageRequest(TypedDict):
    role: MessageRole
    content: str
    session_id: NotRequired[str]
    case_id: NotRequired[str]
    include_assistant_facts: NotRequired[bool]


class MessageResponse(TypedDict):
    case_id: str
    session_id: str
    messages_processed: int
    events_submitted: int
    buffered: bool
    buffer_size: int
    compaction: Optional[ConversationCompactionResult]


# -- Code Intelligence --------------------------------------------------------


class CodeFileEventRequest(TypedDict):
    agent_id: AgentId
    agent_type: str
    session_id: SessionId
    file_path: str
    content: str
    language: NotRequired[str]
    repository: NotRequired[str]
    git_ref: NotRequired[str]
    enable_ast: NotRequired[bool]
    enable_semantic: NotRequired[bool]


class CodeReviewEventRequest(TypedDict):
    agent_id: AgentId
    agent_type: str
    session_id: SessionId
    review_id: str
    action: CodeReviewAction
    body: str
    file_path: NotRequired[str]
    line_range: NotRequired[Tuple[int, int]]
    repository: str
    title: NotRequired[str]
    enable_semantic: NotRequired[bool]


class CodeSearchRequest(TypedDict, total=False):
    name_pattern: str
    kind: CodeSearchKind
    language: str
    file_pattern: str
    limit: int


class CodeEntity(TypedDict):
    name: str
    qualified_name: str
    kind: str
    file_path: str
    language: str
    line_range: Tuple[int, int]
    signature: Optional[str]
    doc_comment: Optional[str]
    visibility: Optional[str]


class CodeSearchResponse(TypedDict):
    entities: List[CodeEntity]
    total_matches: int


# -- Structured Memory --------------------------------------------------------


class LedgerEntry(TypedDict):
    amount: float
    description: str
    direction: LedgerDirection


class StructuredMemoryUpsertRequest(TypedDict):
    key: str
    template: StructuredMemoryTemplate


class StructuredMemoryListResponse(TypedDict):
    keys: List[str]
    count: int


class StructuredMemoryGetResponse(TypedDict):
    key: str
    template: StructuredMemoryTemplate


class StructuredMemoryDeleteResponse(TypedDict):
    success: bool
    key: str


class LedgerAppendRequest(TypedDict):
    amount: float
    description: str
    direction: LedgerDirection


class LedgerAppendResponse(TypedDict):
    success: bool
    balance: float


class LedgerBalanceResponse(TypedDict):
    key: str
    balance: float


class StateTransitionRequest(TypedDict):
    new_state: str
    trigger: str


class StateTransitionResponse(TypedDict):
    success: bool
    new_state: str


class StateCurrentResponse(TypedDict):
    key: str
    current_state: str


class PreferenceUpdateRequest(TypedDict):
    item: str
    rank: int
    score: NotRequired[float]


class PreferenceUpdateResponse(TypedDict):
    success: bool


class TreeAddChildRequest(TypedDict):
    parent: str
    child: str


class TreeAddChildResponse(TypedDict):
    success: bool


# -- MinnsQL ------------------------------------------------------------------


class MinnsQLRequest(TypedDict):
    query: str
    group_id: NotRequired[str]


class MinnsQLStats(TypedDict):
    nodes_scanned: int
    edges_traversed: int
    execution_time_ms: float


class MinnsQLResponse(TypedDict):
    columns: List[str]
    rows: List[List[Any]]
    stats: MinnsQLStats


# -- Reactive Subscriptions ---------------------------------------------------


class SubscriptionCreateRequest(TypedDict):
    query: str
    group_id: NotRequired[str]


class SubscriptionInitialResult(TypedDict):
    columns: List[str]
    rows: List[List[Any]]


class SubscriptionCreateResponse(TypedDict):
    subscription_id: str
    initial: SubscriptionInitialResult
    strategy: str


class SubscriptionInfo(TypedDict):
    subscription_id: str
    query: str
    strategy: str
    cached_row_count: int


class SubscriptionListResponse(TypedDict):
    subscriptions: List[SubscriptionInfo]


class SubscriptionUpdate(TypedDict):
    subscription_id: str
    inserts: List[List[Any]]
    deletes: List[List[Any]]
    count: Optional[int]
    was_full_rerun: bool


class SubscriptionPollResponse(TypedDict):
    updates: List[SubscriptionUpdate]


class SubscriptionDeleteResponse(TypedDict):
    unsubscribed: bool


# -- Temporal Tables ----------------------------------------------------------


class TableColumnDef(TypedDict):
    name: str
    col_type: ColumnType
    nullable: NotRequired[bool]
    primary_key: NotRequired[bool]
    autoincrement: NotRequired[bool]
    default_value: NotRequired[Any]


class TableCreateRequest(TypedDict):
    name: str
    columns: List[TableColumnDef]
    constraints: NotRequired[List[TableConstraint]]


class TableCreateResponse(TypedDict):
    table_id: int
    name: str


class TableSchemaColumn(TypedDict):
    name: str
    col_type: str
    nullable: bool
    autoincrement: bool
    default_value: NotRequired[Any]


class TableSchema(TypedDict):
    table_id: int
    name: str
    columns: List[TableSchemaColumn]
    constraints: List[TableConstraint]


class TableDropResponse(TypedDict):
    table_id: int
    dropped: bool


class TableRowInsertRequest(TypedDict):
    group_id: NotRequired[str]
    values: List[Any]


class TableRowInsertResponse(TypedDict):
    row_id: int
    version_id: int


class TableRowUpdateRequest(TypedDict):
    group_id: NotRequired[str]
    values: List[Any]


class TableRowUpdateResponse(TypedDict):
    old_version_id: int
    new_version_id: int


class TableRowDeleteResponse(TypedDict):
    version_id: int


class TableRowScanQuery(TypedDict, total=False):
    when: TemporalWhen
    as_of: str
    group_id: str
    limit: int
    offset: int


class TableRow(TypedDict):
    row_id: int
    version_id: int
    group_id: str
    valid_from: str
    valid_until: Optional[str]
    values: List[Any]


class TableRowScanResponse(TypedDict):
    count: int
    rows: List[TableRow]


class TableCompactResponse(TypedDict):
    versions_removed: int
    pages_compacted: int


class TableStatsResponse(TypedDict):
    name: str
    active_rows: int
    total_versions: int
    pages: int
    generation: int


# -- Workflows ----------------------------------------------------------------


class WorkflowStepDef(TypedDict):
    id: str
    role: str
    task: str
    depends_on: NotRequired[List[str]]
    inputs: NotRequired[Dict[str, Any]]
    outputs: NotRequired[Dict[str, Any]]
    metadata: NotRequired[Dict[str, Any]]


class WorkflowCreateRequest(TypedDict):
    name: str
    intent: NotRequired[str]
    description: NotRequired[str]
    steps: List[WorkflowStepDef]
    group_id: NotRequired[str]
    metadata: NotRequired[Dict[str, Any]]


class WorkflowCreateResponse(TypedDict):
    success: bool
    workflow_id: str
    workflow_name: str
    nodes_created: int
    edges_created: int
    step_node_ids: Dict[str, int]


class WorkflowSummary(TypedDict):
    workflow_id: str
    name: str
    intent: NotRequired[str]
    step_count: int
    group_id: str
    created_at: str
    active: bool


class WorkflowListResponse(TypedDict):
    workflows: List[WorkflowSummary]
    count: int


class WorkflowStepDetail(TypedDict):
    node_id: int
    id: str
    role: str
    task: str
    depends_on: List[str]
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    state: Optional[str]
    metadata: Dict[str, Any]


class WorkflowDetailResponse(TypedDict):
    workflow_id: str
    name: str
    intent: NotRequired[str]
    description: NotRequired[str]
    group_id: str
    created_at: str
    steps: List[WorkflowStepDetail]
    metadata: NotRequired[Dict[str, Any]]


class WorkflowUpdateRequest(TypedDict):
    name: NotRequired[str]
    intent: NotRequired[str]
    description: NotRequired[str]
    steps: List[WorkflowStepDef]
    group_id: NotRequired[str]
    metadata: NotRequired[Dict[str, Any]]


class WorkflowUpdateResponse(TypedDict):
    success: bool
    workflow_id: str
    nodes_created: int
    nodes_superseded: int
    edges_created: int
    edges_superseded: int
    step_node_ids: Dict[str, int]


class WorkflowDeleteResponse(TypedDict):
    success: bool
    workflow_id: str
    edges_superseded: int


class WorkflowStepTransitionRequest(TypedDict):
    state: str
    result: NotRequired[str]


class WorkflowStepTransitionResponse(TypedDict):
    success: bool
    workflow_id: str
    step_id: str
    new_state: str


class WorkflowFeedbackRequest(TypedDict):
    feedback: str
    outcome: WorkflowOutcome


class WorkflowFeedbackResponse(TypedDict):
    success: bool
    workflow_id: str
    feedback_node_id: int


# -- Agent Registry -----------------------------------------------------------


class AgentRegisterRequest(TypedDict):
    agent_id: str
    group_id: str
    repository: str
    capabilities: List[str]


class AgentRegisterResponse(TypedDict):
    agent_node_id: int
    repo_node_id: int
    status: str


class AgentInfo(TypedDict):
    node_id: int
    agent_id: str
    group_id: str
    repositories: List[str]
    capabilities: List[str]
    last_seen: int


class AgentListResponse(TypedDict):
    agents: List[AgentInfo]


# -- Ontology Evolution -------------------------------------------------------


class OntologyProperty(TypedDict):
    property_name: str
    domain: str
    range: str
    is_symmetric: bool
    is_functional: bool
    is_append_only: bool
    cascade_dependents: List[str]


class OntologyPropertiesResponse(TypedDict):
    properties: List[OntologyProperty]
    count: int


class OntologyUploadResponse(TypedDict):
    status: str
    properties_registered: int
    cascade_properties_updated: int


class OntologyDiscoverResponse(TypedDict):
    proposals_created: int
    proposal_ids: List[str]
    cascade_properties_updated: int


class OntologyCascadeInferenceResponse(TypedDict):
    status: str
    properties_updated: int


class OntologyObservation(TypedDict):
    predicate: str
    domain: str
    range: str
    count: int
    last_seen: int


class _OntologyObservationStats(TypedDict):
    total_predicates: int
    total_observations: int
    timestamp: int


class OntologyObservationsResponse(TypedDict):
    observations: List[OntologyObservation]
    stats: _OntologyObservationStats


class OntologyProposal(TypedDict):
    id: str
    property_name: str
    domain: str
    range: str
    is_symmetric: bool
    is_functional: bool
    status: str
    confidence: float


class OntologyProposalsResponse(TypedDict):
    proposals: List[OntologyProposal]
    count: int


class OntologyProposalApproveResponse(TypedDict):
    status: str
    properties_registered: int


class OntologyProposalRejectResponse(TypedDict):
    status: str


class OntologyStatsResponse(TypedDict):
    status: str
    total_observations: int
    pending_proposals: int


# -- WASM Agent Modules -------------------------------------------------------


class ModuleUploadRequest(TypedDict):
    name: str
    wasm_base64: str
    permissions: List[str]
    group_id: NotRequired[str]


class ModuleUploadResponse(TypedDict):
    name: str
    module_id: int
    enabled: bool
    permissions: List[str]
    functions: List[str]
    triggers: int


class ModuleInfo(TypedDict):
    name: str
    module_id: str
    enabled: bool
    permissions: List[str]
    functions: List[str]
    triggers: List[Any]


class ModuleDetailResponse(TypedDict):
    name: str
    module_id: int
    enabled: bool
    permissions: List[str]
    functions: List[str]
    triggers: int


class ModuleDeleteResponse(TypedDict):
    deleted: bool


class ModuleCallResponse(TypedDict):
    result_base64: str


class ModuleUsageResponse(TypedDict):
    module_name: str
    total_life_consumed_lo: int
    total_life_consumed_hi: int
    total_calls: int
    total_rows_read: int
    total_rows_written: int
    total_graph_queries: int
    total_http_requests: int
    total_http_bytes: int
    total_subscription_events: int
    period_start: int
    last_updated: int


class ModuleUsageResetResponse(TypedDict):
    previous_period: Dict[str, int]
    reset: bool


class ModuleSchedule(TypedDict):
    schedule_id: int
    cron: str
    function: str
    enabled: bool
    next_run: int
    last_run: int


class ModuleScheduleCreateRequest(TypedDict):
    cron: str
    function: str


class ModuleScheduleCreateResponse(TypedDict):
    schedule_id: int


class ModuleScheduleDeleteResponse(TypedDict):
    deleted: bool


# -- Planning & World Model ---------------------------------------------------


class PlanningStrategiesRequest(TypedDict):
    goal_description: str
    goal_bucket_id: int
    context_fingerprint: ContextHash


class StrategyCandidate(TypedDict):
    goal_description: str
    steps: int
    confidence: float
    total_energy: float
    decision: str


class PlanningStrategiesResponse(TypedDict):
    ok: bool
    candidates: List[StrategyCandidate]


class PlanningActionsRequest(TypedDict):
    goal_description: str
    goal_bucket_id: int
    step_index: int
    context_fingerprint: ContextHash


class ActionCandidate(TypedDict):
    action_type: str
    confidence: float
    energy: float
    feasibility: float


class PlanningActionsResponse(TypedDict):
    ok: bool
    actions: List[ActionCandidate]


class PlanningPlanRequest(TypedDict):
    goal_description: str
    goal_bucket_id: int
    context_fingerprint: ContextHash
    session_id: SessionId


class PlanningPlanResponse(TypedDict):
    ok: bool
    mode: str
    goal_description: str
    goal_bucket_id: int
    strategy_candidates: List[StrategyCandidate]
    action_candidates: List[ActionCandidate]


class PlanningExecuteRequest(TypedDict):
    goal_description: str
    goal_bucket_id: int
    context_fingerprint: ContextHash
    session_id: SessionId


class PlanningExecuteResponse(TypedDict):
    ok: bool
    execution_id: int


class PlanningValidateRequest(TypedDict):
    execution_id: int
    event: Event


class PredictionError(TypedDict):
    total_z: float
    event_z: float
    memory_z: float
    strategy_z: float
    mismatch_layer: str


class _RepairResult(TypedDict):
    scope: str
    repaired_actions: int
    repaired_strategies: int


class PlanningValidateResponse(TypedDict):
    ok: bool
    prediction_error: Optional[PredictionError]
    repair_triggered: bool
    repair_result: Optional[_RepairResult]


class _PlanningFlags(TypedDict):
    strategy_generation_enabled: bool
    action_generation_enabled: bool


class WorldModelStatsResponse(TypedDict):
    enabled: bool
    mode: str
    running_mean: NotRequired[float]
    running_variance: NotRequired[float]
    total_scored: NotRequired[int]
    total_trained: NotRequired[int]
    avg_loss: NotRequired[float]
    is_warmed_up: NotRequired[bool]
    planning: _PlanningFlags


# -- Admin --------------------------------------------------------------------


class AdminImportResponse(TypedDict):
    success: bool
    memories_imported: int
    strategies_imported: int
    graph_nodes_imported: int
    graph_edges_imported: int
    total_records: int
    mode: str


# -- Embeddings ---------------------------------------------------------------


class EmbeddingsProcessResponse(TypedDict):
    claims_processed: int
    success: bool


# -- API Keys -----------------------------------------------------------------


class ApiKeyCreateRequest(TypedDict):
    name: str
    group_id: NotRequired[str]
    permissions: NotRequired[List[str]]


class ApiKeyCreateResponse(TypedDict):
    key: str
    name: str
    group_id: NotRequired[str]
    permissions: List[str]
    warning: str


class ApiKeyInfo(TypedDict):
    name: str
    group_id: NotRequired[str]
    permissions: List[str]
    enabled: bool
    created_at: str


class ApiKeyDeleteResponse(TypedDict):
    deleted: bool


# -- PAL cycle helpers --------------------------------------------------------


class RecallContextResult(TypedDict):
    strategies: List[Any]
    memories: List[Any]
    claims: List[Any]
    recall_ms: int


class PerceiveActLearnResult(TypedDict):
    recall: RecallContextResult
    intent: Any
    assistant_response: str
    event_ids: List[str]
    total_ms: int


# -- Client-side types (not wire types) ---------------------------------------


class LocalAck(TypedDict):
    success: bool
    queued: bool
    event_id: str


class TelemetryData(TypedDict, total=False):
    type: str
    path: str
    method: str
    duration_ms: float
    status_code: int
    error: str
    token_count: int
    metadata: Dict[str, Any]
    agent_id: AgentId
    session_id: SessionId

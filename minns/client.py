"""Synchronous and asynchronous Minns API clients.

Usage::

    # Synchronous
    from minns import MinnsClient

    with MinnsClient(api_key="sk-...") as client:
        health = client.health_check()
        result = client.query("What are Alice's connections?")

    # Asynchronous
    from minns import AsyncMinnsClient

    async with AsyncMinnsClient(api_key="sk-...") as client:
        health = await client.health_check()
        result = await client.query("What are Alice's connections?")
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Union, overload
from urllib.parse import quote, urlencode

import httpx

from ._utils import safe_stringify, strip_none
from .builder import EventBuilder
from .errors import MinnsError
from .intent_registry import IntentSpec, ParsedSidecarIntent
from .intent_sidecar import extract_intent_and_response
from .types import (
    AdminImportResponse,
    AgentId,
    AgentListResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AnalyticsResponse,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyDeleteResponse,
    ApiKeyInfo,
    CausalPathResponse,
    CentralityResponse,
    ClaimResponse,
    ClaimSearchRequest,
    ClaimSearchResponse,
    CodeFileEventRequest,
    CodeReviewEventRequest,
    CodeSearchRequest,
    CodeSearchResponse,
    CommunityDetectionResponse,
    ContextHash,
    ContextMemoriesRequest,
    ConversationIngestRequest,
    ConversationIngestResponse,
    EmbeddingsProcessResponse,
    EpisodeResponse,
    Event,
    EventContext,
    Goal,
    GraphContextQuery,
    GraphImportRequest,
    GraphImportResponse,
    GraphNodeQueryRequest,
    GraphNodeQueryResponse,
    GraphPersistResponse,
    GraphQuery,
    GraphResponse,
    GraphTraverseQuery,
    GraphTraverseResponse,
    HealthResponse,
    IndexStatsResponse,
    LedgerAppendRequest,
    LedgerAppendResponse,
    LedgerBalanceResponse,
    LocalAck,
    MemoryResponse,
    MessageRequest,
    MessageResponse,
    MinnsQLResponse,
    ModuleDeleteResponse,
    ModuleCallResponse,
    ModuleDetailResponse,
    ModuleInfo,
    ModuleSchedule,
    ModuleScheduleCreateRequest,
    ModuleScheduleCreateResponse,
    ModuleScheduleDeleteResponse,
    ModuleUploadRequest,
    ModuleUploadResponse,
    ModuleUsageResetResponse,
    ModuleUsageResponse,
    NLQRequest,
    NLQResponse,
    OntologyCascadeInferenceResponse,
    OntologyDiscoverResponse,
    OntologyObservationsResponse,
    OntologyProposal,
    OntologyProposalApproveResponse,
    OntologyProposalRejectResponse,
    OntologyProposalsResponse,
    OntologyPropertiesResponse,
    OntologyStatsResponse,
    OntologyUploadResponse,
    PPRResponse,
    PerceiveActLearnResult,
    PlanningActionsRequest,
    PlanningActionsResponse,
    PlanningExecuteRequest,
    PlanningExecuteResponse,
    PlanningPlanRequest,
    PlanningPlanResponse,
    PlanningStrategiesRequest,
    PlanningStrategiesResponse,
    PlanningValidateRequest,
    PlanningValidateResponse,
    PreferenceUpdateRequest,
    PreferenceUpdateResponse,
    ProcessEventResponse,
    ReachabilityResponse,
    RecallContextResult,
    SearchMode,
    SearchRequest,
    SearchResponse,
    SessionId,
    SimilarStrategyResponse,
    SimpleEventRequest,
    StateChangeEventRequest,
    StateCurrentResponse,
    StateTransitionRequest,
    StateTransitionResponse,
    StatsResponse,
    StrategySimilarityRequest,
    StrategyResponse,
    StructuredMemoryDeleteResponse,
    StructuredMemoryGetResponse,
    StructuredMemoryListResponse,
    StructuredMemoryUpsertRequest,
    SubscriptionCreateResponse,
    SubscriptionDeleteResponse,
    SubscriptionListResponse,
    SubscriptionPollResponse,
    TableCompactResponse,
    TableCreateRequest,
    TableCreateResponse,
    TableDropResponse,
    TableRowInsertRequest,
    TableRowInsertResponse,
    TableRowScanQuery,
    TableRowScanResponse,
    TableRowUpdateRequest,
    TableRowUpdateResponse,
    TableRowDeleteResponse,
    TableSchema,
    TableStatsResponse,
    TelemetryData,
    TransactionEventRequest,
    TreeAddChildRequest,
    TreeAddChildResponse,
    UInt64,
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowDeleteResponse,
    WorkflowDetailResponse,
    WorkflowFeedbackRequest,
    WorkflowFeedbackResponse,
    WorkflowListResponse,
    WorkflowStepTransitionRequest,
    WorkflowStepTransitionResponse,
    WorkflowUpdateRequest,
    WorkflowUpdateResponse,
    WorldModelStatsResponse,
)

BASE_URL = "https://minns.ai"
_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_PAYLOAD = 1024 * 1024  # 1 MB
_DEFAULT_MAX_QUEUE = 1000
_DEFAULT_BATCH_INTERVAL = 0.1  # seconds
_DEFAULT_BATCH_MAX_SIZE = 10


# ============================================================================
# Synchronous client
# ============================================================================


class MinnsClient:
    """Synchronous Minns API client backed by :class:`httpx.Client`."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        agent_id: AgentId | None = None,
        session_id: SessionId | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        headers: Dict[str, str] | None = None,
        on_telemetry: Callable[[TelemetryData], None] | None = None,
        enable_default_telemetry: bool = False,
        debug: bool = False,
        max_payload_size: int = _DEFAULT_MAX_PAYLOAD,
        max_queue_size: int = _DEFAULT_MAX_QUEUE,
        default_async: bool = False,
        auto_batch: bool = False,
        batch_interval: float = _DEFAULT_BATCH_INTERVAL,
        batch_max_size: int = _DEFAULT_BATCH_MAX_SIZE,
        enable_semantic: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_agent_id = agent_id
        self._default_session_id = session_id
        self._on_telemetry = on_telemetry
        self._enable_default_telemetry = enable_default_telemetry
        self._debug = debug
        self._max_payload_size = max_payload_size
        self._max_queue_size = max_queue_size
        self._default_async = default_async
        self._auto_batch = auto_batch
        self._batch_interval = batch_interval
        self._batch_max_size = batch_max_size
        self._enable_semantic = enable_semantic

        self._event_buffer: List[Event] = []
        self._flush_timer: threading.Timer | None = None

        merged_headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if headers:
            merged_headers.update(headers)

        self._http = httpx.Client(
            base_url=self._base_url,
            headers=merged_headers,
            timeout=timeout,
        )

    # -- context manager ------------------------------------------------------

    def __enter__(self) -> MinnsClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Flush pending events and release resources."""
        self._flush_events()
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None
        self._http.close()

    destroy = close

    # -- telemetry ------------------------------------------------------------

    def _emit_telemetry(self, data: TelemetryData) -> None:
        if self._on_telemetry:
            try:
                self._on_telemetry(data)
            except Exception:
                pass

    # -- low-level request ----------------------------------------------------

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        start = time.monotonic()
        serialized: str | None = None
        if body is not None:
            serialized = safe_stringify(body)
            if self._debug:
                print(f"[Minns] {method} {path}")
                print(f"[Minns] Request Body: {serialized}")
            if len(serialized) > self._max_payload_size:
                raise MinnsError(
                    f"Payload size ({len(serialized)} bytes) exceeds maximum "
                    f"({self._max_payload_size} bytes).",
                    413,
                )

        try:
            response = self._http.request(
                method,
                path,
                content=serialized.encode() if serialized else None,
            )
        except httpx.TimeoutException:
            raise MinnsError("Request timeout", 408)
        except httpx.HTTPError as exc:
            raise MinnsError(str(exc), 500)

        duration_ms = (time.monotonic() - start) * 1000

        if not response.is_success:
            error_msg = f"Request failed with status {response.status_code}"
            details: str | None = None
            try:
                err_json = response.json()
                error_msg = err_json.get("error", error_msg)
                details = err_json.get("details")
            except Exception:
                raw = response.text
                if raw:
                    error_msg += f": {raw}"
            self._emit_telemetry(
                {"type": "error", "path": path, "method": method,
                 "status_code": response.status_code, "error": error_msg,
                 "duration_ms": duration_ms}
            )
            raise MinnsError(error_msg, response.status_code, details)

        if response.status_code == 204:
            self._emit_telemetry(
                {"type": "request", "path": path, "method": method,
                 "status_code": 204, "duration_ms": duration_ms}
            )
            return None

        data = response.json()
        if self._debug:
            print(f"[Minns] Response [{response.status_code}]: {safe_stringify(data)}")
        self._emit_telemetry(
            {"type": "request", "path": path, "method": method,
             "status_code": response.status_code, "duration_ms": duration_ms}
        )
        return data

    # -- builder factory ------------------------------------------------------

    def event(
        self,
        agent_type: str,
        *,
        agent_id: AgentId | None = None,
        session_id: SessionId | None = None,
        enable_semantic: bool | None = None,
    ) -> EventBuilder:
        """Create a fluent :class:`EventBuilder`."""
        return EventBuilder(
            self,
            agent_type,
            agent_id=agent_id if agent_id is not None else self._default_agent_id,
            session_id=session_id if session_id is not None else self._default_session_id,
            enable_semantic=enable_semantic if enable_semantic is not None else self._enable_semantic,
        )

    # ========================================================================
    # Event Processing
    # ========================================================================

    def process_event(
        self,
        event: Event,
        *,
        enable_semantic: bool | None = None,
        force_async: bool = False,
    ) -> ProcessEventResponse:
        """Process a single event through the full pipeline."""
        if self._auto_batch and not force_async:
            if len(self._event_buffer) >= self._max_queue_size:
                raise MinnsError("Local event queue is full.", 429)
            self._event_buffer.append(event)
            if len(self._event_buffer) >= self._batch_max_size:
                self._flush_events(enable_semantic=enable_semantic)
            elif self._flush_timer is None:
                self._flush_timer = threading.Timer(
                    self._batch_interval,
                    self._flush_events,
                    kwargs={"enable_semantic": enable_semantic},
                )
                self._flush_timer.daemon = True
                self._flush_timer.start()
            return self._local_ack(str(event.get("id", "queued")), True)

        return self._request("POST", "/api/events", strip_none({
            "event": event,
            "enable_semantic": enable_semantic,
        }))

    def process_events(
        self,
        events: Sequence[Event],
        *,
        enable_semantic: bool | None = None,
    ) -> ProcessEventResponse:
        """Batch-process events (chunked by ``batch_max_size``)."""
        if not events:
            return self._local_ack("empty", False)
        for i in range(0, len(events), self._batch_max_size):
            chunk = events[i : i + self._batch_max_size]
            self._request("POST", "/api/events/batch", strip_none({
                "events": list(chunk),
                "enable_semantic": enable_semantic,
            }))
        return self._local_ack("batch", False)

    def flush(self, *, enable_semantic: bool | None = None) -> None:
        """Manually flush the local event buffer."""
        self._flush_events(enable_semantic=enable_semantic)

    def _flush_events(self, *, enable_semantic: bool | None = None) -> None:
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None
        if not self._event_buffer:
            return
        to_send = list(self._event_buffer)
        self._event_buffer.clear()
        try:
            self.process_events(to_send, enable_semantic=enable_semantic)
            self._emit_telemetry({"type": "batch_flush", "metadata": {"count": len(to_send)}})
        except Exception as exc:
            self._emit_telemetry({"type": "error", "error": str(exc),
                                  "metadata": {"count": len(to_send)}})

    @staticmethod
    def _local_ack(event_id: str, queued: bool) -> ProcessEventResponse:
        return {  # type: ignore[return-value]
            "success": True,
            "nodes_created": 0,
            "patterns_detected": 0,
            "processing_time_ms": 0,
            "event_id": event_id,
        }

    # ========================================================================
    # Events
    # ========================================================================

    def get_events(self, limit: int = 10) -> List[Event]:
        return self._request("GET", f"/api/events?limit={limit}")

    def send_simple_event(self, request: SimpleEventRequest) -> ProcessEventResponse:
        return self._request("POST", "/api/events/simple", request)

    def send_state_change_event(self, request: StateChangeEventRequest) -> ProcessEventResponse:
        return self._request("POST", "/api/events/state-change", request)

    def send_transaction_event(self, request: TransactionEventRequest) -> ProcessEventResponse:
        # Map Python field names to wire format
        body = dict(request)
        if "from_entity" in body:
            body["from"] = body.pop("from_entity")
        if "to_entity" in body:
            body["to"] = body.pop("to_entity")
        return self._request("POST", "/api/events/transaction", body)

    # ========================================================================
    # Episodes
    # ========================================================================

    def get_episodes(self, limit: int = 10) -> List[EpisodeResponse]:
        return self._request("GET", f"/api/episodes?limit={limit}")

    # ========================================================================
    # Memory
    # ========================================================================

    def get_agent_memories(self, agent_id: AgentId, limit: int = 10) -> List[MemoryResponse]:
        return self._request("GET", f"/api/memories/agent/{agent_id}?limit={limit}")

    def get_context_memories(
        self,
        context: EventContext,
        *,
        limit: int = 10,
        min_similarity: float | None = None,
        agent_id: AgentId | None = None,
        session_id: SessionId | None = None,
    ) -> List[MemoryResponse]:
        return self._request("POST", "/api/memories/context", strip_none({
            "context": context,
            "limit": limit,
            "min_similarity": min_similarity,
            "agent_id": agent_id,
            "session_id": session_id,
        }))

    # ========================================================================
    # Strategies
    # ========================================================================

    def get_agent_strategies(self, agent_id: AgentId, limit: int = 10) -> List[StrategyResponse]:
        return self._request("GET", f"/api/strategies/agent/{agent_id}?limit={limit}")

    def get_similar_strategies(self, request: StrategySimilarityRequest) -> List[SimilarStrategyResponse]:
        return self._request("POST", "/api/strategies/similar", request)

    def get_action_suggestions(
        self,
        context_hash: ContextHash,
        last_action_node: int | None = None,
        limit: int = 5,
    ) -> List[Any]:
        params: Dict[str, str] = {"context_hash": str(context_hash), "limit": str(limit)}
        if last_action_node is not None:
            params["last_action_node"] = str(last_action_node)
        return self._request("GET", f"/api/suggestions?{urlencode(params)}")

    # ========================================================================
    # System
    # ========================================================================

    def health_check(self) -> HealthResponse:
        return self._request("GET", "/api/health")

    def get_stats(self) -> StatsResponse:
        return self._request("GET", "/api/stats")

    # ========================================================================
    # Claims
    # ========================================================================

    def get_claims(
        self,
        *,
        limit: int | None = None,
        event_id: UInt64 | None = None,
    ) -> List[ClaimResponse]:
        params: Dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        if event_id is not None:
            params["event_id"] = str(event_id)
        qs = f"?{urlencode(params)}" if params else ""
        return self._request("GET", f"/api/claims{qs}")

    def get_claim_by_id(self, claim_id: UInt64) -> ClaimResponse:
        return self._request("GET", f"/api/claims/{claim_id}")

    def search_claims(self, request: ClaimSearchRequest) -> ClaimSearchResponse:
        return self._request("POST", "/api/claims/search", request)

    def process_embeddings(self, limit: int | None = None) -> EmbeddingsProcessResponse:
        qs = f"?limit={limit}" if limit is not None else ""
        return self._request("POST", f"/api/embeddings/process{qs}")

    # ========================================================================
    # Search
    # ========================================================================

    @overload
    def search(self, query: str) -> SearchResponse: ...
    @overload
    def search(self, query: SearchRequest) -> SearchResponse: ...

    def search(self, query: str | SearchRequest) -> SearchResponse:
        """Keyword / Semantic / Hybrid search. Pass a string for hybrid default."""
        payload: SearchRequest = (
            {"query": query, "mode": "hybrid"} if isinstance(query, str) else query
        )
        return self._request("POST", "/api/search", payload)

    # ========================================================================
    # NLQ
    # ========================================================================

    @overload
    def query(self, question: str) -> NLQResponse: ...
    @overload
    def query(self, question: NLQRequest) -> NLQResponse: ...

    def query(self, question: str | NLQRequest) -> NLQResponse:
        """Natural language query. Pass a string or full NLQRequest."""
        payload: NLQRequest = (
            {"question": question} if isinstance(question, str) else question
        )
        return self._request("POST", "/api/nlq", payload)

    def nlq(self, question: str | NLQRequest) -> NLQResponse:
        """Deprecated alias for :pymethod:`query`."""
        return self.query(question)  # type: ignore[arg-type]

    # ========================================================================
    # Graph
    # ========================================================================

    def get_graph(self, query: GraphQuery | None = None) -> GraphResponse:
        params: Dict[str, str] = {}
        if query:
            if "limit" in query:
                params["limit"] = str(query["limit"])
            if "session_id" in query:
                params["session_id"] = str(query["session_id"])
            if "agent_type" in query:
                params["agent_type"] = query["agent_type"]
        qs = f"?{urlencode(params)}" if params else ""
        return self._request("GET", f"/api/graph{qs}")

    def get_graph_by_context(self, query: GraphContextQuery) -> GraphResponse:
        params: Dict[str, str] = {"context_hash": str(query["context_hash"])}
        if "limit" in query:
            params["limit"] = str(query["limit"])
        if "session_id" in query:
            params["session_id"] = str(query["session_id"])
        if "agent_type" in query:
            params["agent_type"] = query["agent_type"]
        return self._request("GET", f"/api/graph/context?{urlencode(params)}")

    def query_graph_nodes(self, request: GraphNodeQueryRequest) -> GraphNodeQueryResponse:
        return self._request("POST", "/api/graph/query", request)

    def traverse_graph(self, query: GraphTraverseQuery) -> GraphTraverseResponse:
        params: Dict[str, str] = {"start": query["start"]}
        if "max_depth" in query:
            params["max_depth"] = str(query["max_depth"])
        if "node_types" in query:
            params["node_types"] = ",".join(query["node_types"])
        return self._request("GET", f"/api/graph/traverse?{urlencode(params)}")

    def persist_graph(self) -> GraphPersistResponse:
        return self._request("POST", "/api/graph/persist")

    def import_graph(self, request: GraphImportRequest) -> GraphImportResponse:
        return self._request("POST", "/api/graph/import", request)

    # ========================================================================
    # Analytics
    # ========================================================================

    def get_analytics(self) -> AnalyticsResponse:
        return self._request("GET", "/api/analytics")

    def get_communities(self, algorithm: str | None = None) -> CommunityDetectionResponse:
        qs = f"?algorithm={algorithm}" if algorithm else ""
        return self._request("GET", f"/api/communities{qs}")

    def get_centrality(self, limit: int | None = None) -> CentralityResponse:
        qs = f"?limit={limit}" if limit is not None else ""
        return self._request("GET", f"/api/centrality{qs}")

    def get_personalized_page_rank(
        self,
        source_node_id: int,
        *,
        limit: int | None = None,
        min_score: float | None = None,
    ) -> PPRResponse:
        params: Dict[str, str] = {"source_node_id": str(source_node_id)}
        if limit is not None:
            params["limit"] = str(limit)
        if min_score is not None:
            params["min_score"] = str(min_score)
        return self._request("GET", f"/api/ppr?{urlencode(params)}")

    def get_reachability(
        self,
        source: int,
        *,
        max_hops: int | None = None,
        max_results: int | None = None,
    ) -> ReachabilityResponse:
        params: Dict[str, str] = {"source": str(source)}
        if max_hops is not None:
            params["max_hops"] = str(max_hops)
        if max_results is not None:
            params["max_results"] = str(max_results)
        return self._request("GET", f"/api/reachability?{urlencode(params)}")

    def get_causal_path(self, source: int, target: int) -> CausalPathResponse:
        return self._request(
            "GET", f"/api/causal-path?{urlencode({'source': source, 'target': target})}"
        )

    def get_index_stats(self) -> List[IndexStatsResponse]:
        return self._request("GET", "/api/indexes")

    # ========================================================================
    # Conversation Ingestion
    # ========================================================================

    def ingest_conversations(self, request: ConversationIngestRequest) -> ConversationIngestResponse:
        return self._request("POST", "/api/conversations/ingest", request)

    def send_message(self, request: MessageRequest) -> MessageResponse:
        return self._request("POST", "/api/messages", request)

    # ========================================================================
    # Code Intelligence
    # ========================================================================

    def send_code_file_event(self, request: CodeFileEventRequest) -> ProcessEventResponse:
        return self._request("POST", "/api/events/code-file", request)

    def send_code_review_event(self, request: CodeReviewEventRequest) -> ProcessEventResponse:
        return self._request("POST", "/api/events/code-review", request)

    def search_code(self, request: CodeSearchRequest | None = None) -> CodeSearchResponse:
        return self._request("POST", "/api/code/search", request or {})

    # ========================================================================
    # Structured Memory
    # ========================================================================

    def upsert_structured_memory(self, request: StructuredMemoryUpsertRequest) -> None:
        self._request("POST", "/api/structured-memory", request)

    def list_structured_memory(self, prefix: str | None = None) -> StructuredMemoryListResponse:
        qs = f"?prefix={quote(prefix)}" if prefix else ""
        return self._request("GET", f"/api/structured-memory{qs}")

    def get_structured_memory(self, key: str) -> StructuredMemoryGetResponse:
        return self._request("GET", f"/api/structured-memory/{quote(key)}")

    def delete_structured_memory(self, key: str) -> StructuredMemoryDeleteResponse:
        return self._request("DELETE", f"/api/structured-memory/{quote(key)}")

    def append_ledger_entry(self, key: str, entry: LedgerAppendRequest) -> LedgerAppendResponse:
        return self._request("POST", f"/api/structured-memory/ledger/{quote(key)}/append", entry)

    def get_ledger_balance(self, key: str) -> LedgerBalanceResponse:
        return self._request("GET", f"/api/structured-memory/ledger/{quote(key)}/balance")

    def transition_state(self, key: str, request: StateTransitionRequest) -> StateTransitionResponse:
        return self._request("POST", f"/api/structured-memory/state/{quote(key)}/transition", request)

    def get_current_state(self, key: str) -> StateCurrentResponse:
        return self._request("GET", f"/api/structured-memory/state/{quote(key)}/current")

    def update_preference(self, key: str, request: PreferenceUpdateRequest) -> PreferenceUpdateResponse:
        return self._request("POST", f"/api/structured-memory/preference/{quote(key)}/update", request)

    def add_tree_child(self, key: str, request: TreeAddChildRequest) -> TreeAddChildResponse:
        return self._request("POST", f"/api/structured-memory/tree/{quote(key)}/add-child", request)

    # ========================================================================
    # MinnsQL
    # ========================================================================

    def execute_query(self, query: str, group_id: str | None = None) -> MinnsQLResponse:
        return self._request("POST", "/api/query", strip_none({
            "query": query, "group_id": group_id,
        }))

    # ========================================================================
    # Reactive Subscriptions
    # ========================================================================

    def create_subscription(self, query: str, group_id: str | None = None) -> SubscriptionCreateResponse:
        return self._request("POST", "/api/subscriptions", strip_none({
            "query": query, "group_id": group_id,
        }))

    def list_subscriptions(self) -> SubscriptionListResponse:
        return self._request("GET", "/api/subscriptions")

    def poll_subscription(self, subscription_id: str | int) -> SubscriptionPollResponse:
        return self._request("GET", f"/api/subscriptions/{subscription_id}/poll")

    def delete_subscription(self, subscription_id: str | int) -> SubscriptionDeleteResponse:
        return self._request("DELETE", f"/api/subscriptions/{subscription_id}")

    # ========================================================================
    # Temporal Tables
    # ========================================================================

    def create_table(self, request: TableCreateRequest) -> TableCreateResponse:
        return self._request("POST", "/api/tables", request)

    def list_tables(self) -> List[TableSchema]:
        return self._request("GET", "/api/tables")

    def get_table_schema(self, name: str) -> TableSchema:
        return self._request("GET", f"/api/tables/{quote(name)}/schema")

    def drop_table(self, name: str) -> TableDropResponse:
        return self._request("DELETE", f"/api/tables/{quote(name)}")

    def insert_rows(
        self,
        table: str,
        rows: TableRowInsertRequest | List[TableRowInsertRequest],
    ) -> TableRowInsertResponse | List[TableRowInsertResponse]:
        return self._request("POST", f"/api/tables/{quote(table)}/rows", rows)

    def update_row(self, table: str, row_id: int, request: TableRowUpdateRequest) -> TableRowUpdateResponse:
        return self._request("PUT", f"/api/tables/{quote(table)}/rows/{row_id}", request)

    def delete_row(self, table: str, row_id: int) -> TableRowDeleteResponse:
        return self._request("DELETE", f"/api/tables/{quote(table)}/rows/{row_id}")

    def scan_rows(self, table: str, query: TableRowScanQuery | None = None) -> TableRowScanResponse:
        params: Dict[str, str] = {}
        if query:
            for k in ("when", "as_of", "group_id", "limit", "offset"):
                v = query.get(k)  # type: ignore[literal-required]
                if v is not None:
                    params[k] = str(v)
        qs = f"?{urlencode(params)}" if params else ""
        return self._request("GET", f"/api/tables/{quote(table)}/rows{qs}")

    def get_rows_by_node(self, table: str, node_id: int, group_id: int | None = None) -> TableRowScanResponse:
        qs = f"?group_id={group_id}" if group_id is not None else ""
        return self._request("GET", f"/api/tables/{quote(table)}/by-node/{node_id}{qs}")

    def compact_table(self, table: str) -> TableCompactResponse:
        return self._request("POST", f"/api/tables/{quote(table)}/compact")

    def get_table_stats(self, table: str) -> TableStatsResponse:
        return self._request("GET", f"/api/tables/{quote(table)}/stats")

    # ========================================================================
    # Workflows
    # ========================================================================

    def create_workflow(self, request: WorkflowCreateRequest) -> WorkflowCreateResponse:
        return self._request("POST", "/api/workflows", request)

    def list_workflows(
        self, *, group_id: str | None = None, limit: int | None = None,
    ) -> WorkflowListResponse:
        params: Dict[str, str] = {}
        if group_id:
            params["group_id"] = group_id
        if limit is not None:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._request("GET", f"/api/workflows{qs}")

    def get_workflow(self, workflow_id: str | int) -> WorkflowDetailResponse:
        return self._request("GET", f"/api/workflows/{workflow_id}")

    def update_workflow(self, workflow_id: str | int, request: WorkflowUpdateRequest) -> WorkflowUpdateResponse:
        return self._request("PUT", f"/api/workflows/{workflow_id}", request)

    def delete_workflow(self, workflow_id: str | int) -> WorkflowDeleteResponse:
        return self._request("DELETE", f"/api/workflows/{workflow_id}")

    def transition_workflow_step(
        self,
        workflow_id: str | int,
        step_id: str,
        request: WorkflowStepTransitionRequest,
    ) -> WorkflowStepTransitionResponse:
        return self._request(
            "POST", f"/api/workflows/{workflow_id}/steps/{quote(step_id)}/transition", request
        )

    def add_workflow_feedback(
        self, workflow_id: str | int, request: WorkflowFeedbackRequest,
    ) -> WorkflowFeedbackResponse:
        return self._request("POST", f"/api/workflows/{workflow_id}/feedback", request)

    # ========================================================================
    # Agent Registry
    # ========================================================================

    def register_agent(self, request: AgentRegisterRequest) -> AgentRegisterResponse:
        return self._request("POST", "/api/agents/register", request)

    def list_agents(self, group_id: str) -> AgentListResponse:
        return self._request("GET", f"/api/agents?{urlencode({'group_id': group_id})}")

    # ========================================================================
    # Ontology Evolution
    # ========================================================================

    def get_ontology_properties(self) -> OntologyPropertiesResponse:
        return self._request("GET", "/api/ontology/properties")

    def upload_ontology(self, ttl: str) -> OntologyUploadResponse:
        return self._request("POST", "/api/ontology/upload", {"ttl": ttl})

    def discover_ontology(self) -> OntologyDiscoverResponse:
        return self._request("POST", "/api/ontology/discover")

    def infer_ontology_cascades(self) -> OntologyCascadeInferenceResponse:
        return self._request("POST", "/api/ontology/cascade-inference")

    def get_ontology_observations(self) -> OntologyObservationsResponse:
        return self._request("GET", "/api/ontology/observations")

    def get_ontology_proposals(self) -> OntologyProposalsResponse:
        return self._request("GET", "/api/ontology/proposals")

    def get_ontology_proposal(self, proposal_id: str | int) -> OntologyProposal:
        return self._request("GET", f"/api/ontology/proposals/{proposal_id}")

    def approve_ontology_proposal(self, proposal_id: str | int) -> OntologyProposalApproveResponse:
        return self._request("POST", f"/api/ontology/proposals/{proposal_id}/approve")

    def reject_ontology_proposal(self, proposal_id: str | int) -> OntologyProposalRejectResponse:
        return self._request("POST", f"/api/ontology/proposals/{proposal_id}/reject")

    def get_ontology_stats(self) -> OntologyStatsResponse:
        return self._request("GET", "/api/ontology/stats")

    # ========================================================================
    # WASM Modules
    # ========================================================================

    def upload_module(self, request: ModuleUploadRequest) -> ModuleUploadResponse:
        return self._request("POST", "/api/modules", request)

    def list_modules(self) -> List[ModuleInfo]:
        return self._request("GET", "/api/modules")

    def get_module(self, name: str) -> ModuleDetailResponse:
        return self._request("GET", f"/api/modules/{quote(name)}")

    def delete_module(self, name: str) -> ModuleDeleteResponse:
        return self._request("DELETE", f"/api/modules/{quote(name)}")

    def call_module_function(
        self, module_name: str, function_name: str, args_base64: str | None = None,
    ) -> ModuleCallResponse:
        body = {"args_base64": args_base64} if args_base64 else None
        return self._request(
            "POST", f"/api/modules/{quote(module_name)}/call/{quote(function_name)}", body,
        )

    def enable_module(self, name: str) -> None:
        self._request("PUT", f"/api/modules/{quote(name)}/enable")

    def disable_module(self, name: str) -> None:
        self._request("PUT", f"/api/modules/{quote(name)}/disable")

    def get_module_usage(self, name: str) -> ModuleUsageResponse:
        return self._request("GET", f"/api/modules/{quote(name)}/usage")

    def reset_module_usage(self, name: str) -> ModuleUsageResetResponse:
        return self._request("POST", f"/api/modules/{quote(name)}/usage/reset")

    def list_module_schedules(self, name: str) -> List[ModuleSchedule]:
        return self._request("GET", f"/api/modules/{quote(name)}/schedules")

    def create_module_schedule(
        self, module_name: str, request: ModuleScheduleCreateRequest,
    ) -> ModuleScheduleCreateResponse:
        return self._request("POST", f"/api/modules/{quote(module_name)}/schedules", request)

    def delete_module_schedule(self, module_name: str, schedule_id: int) -> ModuleScheduleDeleteResponse:
        return self._request("DELETE", f"/api/modules/{quote(module_name)}/schedules/{schedule_id}")

    # ========================================================================
    # Planning & World Model
    # ========================================================================

    def generate_strategies(self, request: PlanningStrategiesRequest) -> PlanningStrategiesResponse:
        return self._request("POST", "/api/planning/strategies", request)

    def generate_actions(self, request: PlanningActionsRequest) -> PlanningActionsResponse:
        return self._request("POST", "/api/planning/actions", request)

    def create_plan(self, request: PlanningPlanRequest) -> PlanningPlanResponse:
        return self._request("POST", "/api/planning/plan", request)

    def plan(self, goal_description: str) -> PlanningPlanResponse:
        """Shorthand — creates a plan from a goal description using client defaults."""
        return self.create_plan({
            "goal_description": goal_description,
            "goal_bucket_id": 0,
            "context_fingerprint": 0,
            "session_id": self._default_session_id or 0,
        })

    def start_execution(self, request: PlanningExecuteRequest) -> PlanningExecuteResponse:
        return self._request("POST", "/api/planning/execute", request)

    def validate_event(self, request: PlanningValidateRequest) -> PlanningValidateResponse:
        return self._request("POST", "/api/planning/validate", request)

    def get_world_model_stats(self) -> WorldModelStatsResponse:
        return self._request("GET", "/api/world-model/stats")

    # ========================================================================
    # Admin
    # ========================================================================

    def export_database(self) -> bytes:
        """Export entire database as binary."""
        response = self._http.post("/api/admin/export")
        if not response.is_success:
            raise MinnsError(f"Export failed with status {response.status_code}", response.status_code)
        return response.content

    def import_database(self, data: bytes, mode: str = "replace") -> AdminImportResponse:
        """Import database from binary."""
        response = self._http.post(
            f"/api/admin/import?mode={mode}",
            content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        if not response.is_success:
            raise MinnsError(f"Import failed with status {response.status_code}", response.status_code)
        return response.json()

    # ========================================================================
    # API Keys
    # ========================================================================

    def create_api_key(self, request: ApiKeyCreateRequest) -> ApiKeyCreateResponse:
        return self._request("POST", "/api/keys", request)

    def list_api_keys(self) -> List[ApiKeyInfo]:
        return self._request("GET", "/api/keys")

    def delete_api_key(self, name: str) -> ApiKeyDeleteResponse:
        return self._request("DELETE", f"/api/keys/{quote(name)}")

    # ========================================================================
    # PAL helpers
    # ========================================================================

    def recall_context(
        self,
        agent_id: AgentId,
        context: EventContext,
        *,
        claims_query: str | None = None,
        memory_limit: int = 5,
        strategy_limit: int = 5,
    ) -> RecallContextResult:
        """Parallel fetch of strategies + memories + claims."""
        start = time.monotonic()
        empty_claims: ClaimSearchResponse = {"groups": [], "ungrouped": [], "total_results": 0}

        try:
            strategies = self.get_agent_strategies(agent_id, strategy_limit)
        except Exception:
            strategies = []
        try:
            memories = self.get_context_memories(context, limit=memory_limit, agent_id=agent_id)
        except Exception:
            memories = []
        try:
            claims_result = (
                self.search_claims({"query_text": claims_query, "top_k": 5})
                if claims_query else empty_claims
            )
        except Exception:
            claims_result = empty_claims

        flat_claims = [
            *[c for g in claims_result.get("groups", []) for c in g.get("claims", [])],
            *claims_result.get("ungrouped", []),
        ]
        return {
            "strategies": strategies,
            "memories": memories,
            "claims": flat_claims,
            "recall_ms": int((time.monotonic() - start) * 1000),
        }

    def perceive_act_learn(
        self,
        agent_type: str,
        agent_id: AgentId,
        session_id: SessionId,
        *,
        message: str,
        model_output: str,
        spec: IntentSpec,
        claims_query: str | None = None,
        memory_limit: int = 5,
        strategy_limit: int = 5,
        context_variables: Dict[str, Any] | None = None,
        goals: List[Dict[str, Any]] | None = None,
        retry: tuple[int, int] | None = None,
        caused_by: str | None = None,
    ) -> PerceiveActLearnResult:
        """Full Perceive-Act-Learn cycle."""
        total_start = time.monotonic()

        goal_list = goals or []
        ctx_goals: List[Goal] = [
            {
                "id": i + 1,
                "description": g.get("text", ""),
                "priority": (g.get("priority", 3)) / 5.0,
                "progress": g.get("progress", 0.0),
                "deadline": None,
                "subgoals": [],
            }
            for i, g in enumerate(goal_list)
        ]
        event_context: EventContext = {
            "environment": {
                "variables": context_variables or {},
                "spatial": None,
                "temporal": {"time_of_day": None, "deadlines": [], "patterns": []},
            },
            "active_goals": ctx_goals,
            "resources": {
                "computational": {"cpu_percent": 0, "memory_bytes": 0, "storage_bytes": 0, "network_bandwidth": 0},
                "external": {},
            },
            "embeddings": None,
        }

        recall = self.recall_context(
            agent_id, event_context,
            claims_query=claims_query,
            memory_limit=memory_limit,
            strategy_limit=strategy_limit,
        )

        intent, assistant_response = extract_intent_and_response(model_output, message, spec)

        event_ids: List[str] = []

        # Observation event
        if intent.perception:
            obs = (
                self.event(agent_type, agent_id=agent_id, session_id=session_id)
                .observation(
                    "perception", vars(intent.perception),
                    confidence=1.0 - (intent.perception.risk or 0),
                    source="llm_parse",
                )
            )
            if caused_by:
                obs.caused_by(caused_by)
            for g in goal_list:
                obs.goal(g.get("text", ""), g.get("priority", 3), g.get("progress", 0.0))
            obs_event = obs.build()
            event_ids.append(str(obs_event.get("id", "")))
            try:
                self.process_event(obs_event, enable_semantic=intent.enable_semantic)
            except Exception:
                pass

        # Action event
        action = (
            self.event(agent_type, agent_id=agent_id, session_id=session_id)
            .action(intent.intent, dict(intent.slots))
        )
        if caused_by:
            action.caused_by(caused_by)
        if retry:
            action.retry(*retry)
        for g in goal_list:
            action.goal(g.get("text", ""), g.get("priority", 3), g.get("progress", 0.0))

        if intent.outcome_capture:
            if intent.outcome_capture.success:
                action.outcome(intent.outcome_capture.observed_result or "ok")
            else:
                action.failure(intent.outcome_capture.error_code or "unknown_error")

        action_event = action.build()
        event_ids.append(str(action_event.get("id", "")))
        try:
            self.process_event(action_event, enable_semantic=intent.enable_semantic)
        except Exception:
            pass

        # Learning Outcome
        learning = (
            self.event(agent_type, agent_id=agent_id, session_id=session_id)
            .learning({"Outcome": {
                "query_id": str(action_event.get("id", "")),
                "success": intent.outcome_capture.success if intent.outcome_capture else True,
            }})
        )
        if caused_by:
            learning.caused_by(caused_by)
        learning_event = learning.build()
        event_ids.append(str(learning_event.get("id", "")))
        try:
            self.process_event(learning_event, enable_semantic=False)
        except Exception:
            pass

        return {
            "recall": recall,
            "intent": intent,
            "assistant_response": assistant_response,
            "event_ids": event_ids,
            "total_ms": int((time.monotonic() - total_start) * 1000),
        }


# ============================================================================
# Async client
# ============================================================================


class AsyncMinnsClient:
    """Asynchronous Minns API client backed by :class:`httpx.AsyncClient`.

    API-identical to :class:`MinnsClient` but every I/O method is a coroutine.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        agent_id: AgentId | None = None,
        session_id: SessionId | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        headers: Dict[str, str] | None = None,
        on_telemetry: Callable[[TelemetryData], None] | None = None,
        enable_default_telemetry: bool = False,
        debug: bool = False,
        max_payload_size: int = _DEFAULT_MAX_PAYLOAD,
        max_queue_size: int = _DEFAULT_MAX_QUEUE,
        auto_batch: bool = False,
        batch_interval: float = _DEFAULT_BATCH_INTERVAL,
        batch_max_size: int = _DEFAULT_BATCH_MAX_SIZE,
        enable_semantic: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_agent_id = agent_id
        self._default_session_id = session_id
        self._on_telemetry = on_telemetry
        self._enable_default_telemetry = enable_default_telemetry
        self._debug = debug
        self._max_payload_size = max_payload_size
        self._max_queue_size = max_queue_size
        self._auto_batch = auto_batch
        self._batch_interval = batch_interval
        self._batch_max_size = batch_max_size
        self._enable_semantic = enable_semantic

        self._event_buffer: List[Event] = []

        merged_headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if headers:
            merged_headers.update(headers)

        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=merged_headers,
            timeout=timeout,
        )

    async def __aenter__(self) -> AsyncMinnsClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._flush_events()
        await self._http.aclose()

    destroy = close

    def _emit_telemetry(self, data: TelemetryData) -> None:
        if self._on_telemetry:
            try:
                self._on_telemetry(data)
            except Exception:
                pass

    async def _request(self, method: str, path: str, body: Any = None) -> Any:
        start = time.monotonic()
        serialized: str | None = None
        if body is not None:
            serialized = safe_stringify(body)
            if self._debug:
                print(f"[Minns] {method} {path}")
                print(f"[Minns] Request Body: {serialized}")
            if len(serialized) > self._max_payload_size:
                raise MinnsError(
                    f"Payload size ({len(serialized)} bytes) exceeds maximum "
                    f"({self._max_payload_size} bytes).",
                    413,
                )
        try:
            response = await self._http.request(
                method, path, content=serialized.encode() if serialized else None,
            )
        except httpx.TimeoutException:
            raise MinnsError("Request timeout", 408)
        except httpx.HTTPError as exc:
            raise MinnsError(str(exc), 500)

        duration_ms = (time.monotonic() - start) * 1000

        if not response.is_success:
            error_msg = f"Request failed with status {response.status_code}"
            details: str | None = None
            try:
                err_json = response.json()
                error_msg = err_json.get("error", error_msg)
                details = err_json.get("details")
            except Exception:
                raw = response.text
                if raw:
                    error_msg += f": {raw}"
            self._emit_telemetry(
                {"type": "error", "path": path, "method": method,
                 "status_code": response.status_code, "error": error_msg,
                 "duration_ms": duration_ms}
            )
            raise MinnsError(error_msg, response.status_code, details)

        if response.status_code == 204:
            self._emit_telemetry(
                {"type": "request", "path": path, "method": method,
                 "status_code": 204, "duration_ms": duration_ms}
            )
            return None

        data = response.json()
        if self._debug:
            print(f"[Minns] Response [{response.status_code}]: {safe_stringify(data)}")
        self._emit_telemetry(
            {"type": "request", "path": path, "method": method,
             "status_code": response.status_code, "duration_ms": duration_ms}
        )
        return data

    # -- builder factory ------------------------------------------------------

    def event(
        self,
        agent_type: str,
        *,
        agent_id: AgentId | None = None,
        session_id: SessionId | None = None,
        enable_semantic: bool | None = None,
    ) -> EventBuilder:
        return EventBuilder(
            self,
            agent_type,
            agent_id=agent_id if agent_id is not None else self._default_agent_id,
            session_id=session_id if session_id is not None else self._default_session_id,
            enable_semantic=enable_semantic if enable_semantic is not None else self._enable_semantic,
        )

    # ========================================================================
    # All async methods mirror the sync client 1:1
    # ========================================================================

    async def process_event(self, event: Event, *, enable_semantic: bool | None = None, force_async: bool = False) -> ProcessEventResponse:
        if self._auto_batch and not force_async:
            if len(self._event_buffer) >= self._max_queue_size:
                raise MinnsError("Local event queue is full.", 429)
            self._event_buffer.append(event)
            if len(self._event_buffer) >= self._batch_max_size:
                await self._flush_events(enable_semantic=enable_semantic)
            return MinnsClient._local_ack(str(event.get("id", "queued")), True)
        return await self._request("POST", "/api/events", strip_none({"event": event, "enable_semantic": enable_semantic}))

    async def process_events(self, events: Sequence[Event], *, enable_semantic: bool | None = None) -> ProcessEventResponse:
        if not events:
            return MinnsClient._local_ack("empty", False)
        for i in range(0, len(events), self._batch_max_size):
            chunk = events[i : i + self._batch_max_size]
            await self._request("POST", "/api/events/batch", strip_none({"events": list(chunk), "enable_semantic": enable_semantic}))
        return MinnsClient._local_ack("batch", False)

    async def flush(self, *, enable_semantic: bool | None = None) -> None:
        await self._flush_events(enable_semantic=enable_semantic)

    async def _flush_events(self, *, enable_semantic: bool | None = None) -> None:
        if not self._event_buffer:
            return
        to_send = list(self._event_buffer)
        self._event_buffer.clear()
        try:
            await self.process_events(to_send, enable_semantic=enable_semantic)
            self._emit_telemetry({"type": "batch_flush", "metadata": {"count": len(to_send)}})
        except Exception as exc:
            self._emit_telemetry({"type": "error", "error": str(exc), "metadata": {"count": len(to_send)}})

    async def get_events(self, limit: int = 10) -> List[Event]:
        return await self._request("GET", f"/api/events?limit={limit}")

    async def send_simple_event(self, request: SimpleEventRequest) -> ProcessEventResponse:
        return await self._request("POST", "/api/events/simple", request)

    async def send_state_change_event(self, request: StateChangeEventRequest) -> ProcessEventResponse:
        return await self._request("POST", "/api/events/state-change", request)

    async def send_transaction_event(self, request: TransactionEventRequest) -> ProcessEventResponse:
        body = dict(request)
        if "from_entity" in body:
            body["from"] = body.pop("from_entity")
        if "to_entity" in body:
            body["to"] = body.pop("to_entity")
        return await self._request("POST", "/api/events/transaction", body)

    async def get_episodes(self, limit: int = 10) -> List[EpisodeResponse]:
        return await self._request("GET", f"/api/episodes?limit={limit}")

    async def get_agent_memories(self, agent_id: AgentId, limit: int = 10) -> List[MemoryResponse]:
        return await self._request("GET", f"/api/memories/agent/{agent_id}?limit={limit}")

    async def get_context_memories(self, context: EventContext, *, limit: int = 10, min_similarity: float | None = None, agent_id: AgentId | None = None, session_id: SessionId | None = None) -> List[MemoryResponse]:
        return await self._request("POST", "/api/memories/context", strip_none({"context": context, "limit": limit, "min_similarity": min_similarity, "agent_id": agent_id, "session_id": session_id}))

    async def get_agent_strategies(self, agent_id: AgentId, limit: int = 10) -> List[StrategyResponse]:
        return await self._request("GET", f"/api/strategies/agent/{agent_id}?limit={limit}")

    async def get_similar_strategies(self, request: StrategySimilarityRequest) -> List[SimilarStrategyResponse]:
        return await self._request("POST", "/api/strategies/similar", request)

    async def get_action_suggestions(self, context_hash: ContextHash, last_action_node: int | None = None, limit: int = 5) -> List[Any]:
        params: Dict[str, str] = {"context_hash": str(context_hash), "limit": str(limit)}
        if last_action_node is not None:
            params["last_action_node"] = str(last_action_node)
        return await self._request("GET", f"/api/suggestions?{urlencode(params)}")

    async def health_check(self) -> HealthResponse:
        return await self._request("GET", "/api/health")

    async def get_stats(self) -> StatsResponse:
        return await self._request("GET", "/api/stats")

    async def get_claims(self, *, limit: int | None = None, event_id: UInt64 | None = None) -> List[ClaimResponse]:
        params: Dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        if event_id is not None:
            params["event_id"] = str(event_id)
        qs = f"?{urlencode(params)}" if params else ""
        return await self._request("GET", f"/api/claims{qs}")

    async def get_claim_by_id(self, claim_id: UInt64) -> ClaimResponse:
        return await self._request("GET", f"/api/claims/{claim_id}")

    async def search_claims(self, request: ClaimSearchRequest) -> ClaimSearchResponse:
        return await self._request("POST", "/api/claims/search", request)

    async def process_embeddings(self, limit: int | None = None) -> EmbeddingsProcessResponse:
        qs = f"?limit={limit}" if limit is not None else ""
        return await self._request("POST", f"/api/embeddings/process{qs}")

    async def search(self, query: str | SearchRequest) -> SearchResponse:
        payload: SearchRequest = {"query": query, "mode": "hybrid"} if isinstance(query, str) else query
        return await self._request("POST", "/api/search", payload)

    async def query(self, question: str | NLQRequest) -> NLQResponse:
        payload: NLQRequest = {"question": question} if isinstance(question, str) else question
        return await self._request("POST", "/api/nlq", payload)

    async def nlq(self, question: str | NLQRequest) -> NLQResponse:
        return await self.query(question)

    async def get_graph(self, query: GraphQuery | None = None) -> GraphResponse:
        params: Dict[str, str] = {}
        if query:
            for k in ("limit", "session_id", "agent_type"):
                v = query.get(k)  # type: ignore[literal-required]
                if v is not None:
                    params[k] = str(v)
        qs = f"?{urlencode(params)}" if params else ""
        return await self._request("GET", f"/api/graph{qs}")

    async def get_graph_by_context(self, query: GraphContextQuery) -> GraphResponse:
        params: Dict[str, str] = {"context_hash": str(query["context_hash"])}
        for k in ("limit", "session_id", "agent_type"):
            v = query.get(k)  # type: ignore[literal-required]
            if v is not None:
                params[k] = str(v)
        return await self._request("GET", f"/api/graph/context?{urlencode(params)}")

    async def query_graph_nodes(self, request: GraphNodeQueryRequest) -> GraphNodeQueryResponse:
        return await self._request("POST", "/api/graph/query", request)

    async def traverse_graph(self, query: GraphTraverseQuery) -> GraphTraverseResponse:
        params: Dict[str, str] = {"start": query["start"]}
        if "max_depth" in query:
            params["max_depth"] = str(query["max_depth"])
        if "node_types" in query:
            params["node_types"] = ",".join(query["node_types"])
        return await self._request("GET", f"/api/graph/traverse?{urlencode(params)}")

    async def persist_graph(self) -> GraphPersistResponse:
        return await self._request("POST", "/api/graph/persist")

    async def import_graph(self, request: GraphImportRequest) -> GraphImportResponse:
        return await self._request("POST", "/api/graph/import", request)

    async def get_analytics(self) -> AnalyticsResponse:
        return await self._request("GET", "/api/analytics")

    async def get_communities(self, algorithm: str | None = None) -> CommunityDetectionResponse:
        qs = f"?algorithm={algorithm}" if algorithm else ""
        return await self._request("GET", f"/api/communities{qs}")

    async def get_centrality(self, limit: int | None = None) -> CentralityResponse:
        qs = f"?limit={limit}" if limit is not None else ""
        return await self._request("GET", f"/api/centrality{qs}")

    async def get_personalized_page_rank(self, source_node_id: int, *, limit: int | None = None, min_score: float | None = None) -> PPRResponse:
        params: Dict[str, str] = {"source_node_id": str(source_node_id)}
        if limit is not None:
            params["limit"] = str(limit)
        if min_score is not None:
            params["min_score"] = str(min_score)
        return await self._request("GET", f"/api/ppr?{urlencode(params)}")

    async def get_reachability(self, source: int, *, max_hops: int | None = None, max_results: int | None = None) -> ReachabilityResponse:
        params: Dict[str, str] = {"source": str(source)}
        if max_hops is not None:
            params["max_hops"] = str(max_hops)
        if max_results is not None:
            params["max_results"] = str(max_results)
        return await self._request("GET", f"/api/reachability?{urlencode(params)}")

    async def get_causal_path(self, source: int, target: int) -> CausalPathResponse:
        return await self._request("GET", f"/api/causal-path?{urlencode({'source': source, 'target': target})}")

    async def get_index_stats(self) -> List[IndexStatsResponse]:
        return await self._request("GET", "/api/indexes")

    async def ingest_conversations(self, request: ConversationIngestRequest) -> ConversationIngestResponse:
        return await self._request("POST", "/api/conversations/ingest", request)

    async def send_message(self, request: MessageRequest) -> MessageResponse:
        return await self._request("POST", "/api/messages", request)

    async def send_code_file_event(self, request: CodeFileEventRequest) -> ProcessEventResponse:
        return await self._request("POST", "/api/events/code-file", request)

    async def send_code_review_event(self, request: CodeReviewEventRequest) -> ProcessEventResponse:
        return await self._request("POST", "/api/events/code-review", request)

    async def search_code(self, request: CodeSearchRequest | None = None) -> CodeSearchResponse:
        return await self._request("POST", "/api/code/search", request or {})

    async def upsert_structured_memory(self, request: StructuredMemoryUpsertRequest) -> None:
        await self._request("POST", "/api/structured-memory", request)

    async def list_structured_memory(self, prefix: str | None = None) -> StructuredMemoryListResponse:
        qs = f"?prefix={quote(prefix)}" if prefix else ""
        return await self._request("GET", f"/api/structured-memory{qs}")

    async def get_structured_memory(self, key: str) -> StructuredMemoryGetResponse:
        return await self._request("GET", f"/api/structured-memory/{quote(key)}")

    async def delete_structured_memory(self, key: str) -> StructuredMemoryDeleteResponse:
        return await self._request("DELETE", f"/api/structured-memory/{quote(key)}")

    async def append_ledger_entry(self, key: str, entry: LedgerAppendRequest) -> LedgerAppendResponse:
        return await self._request("POST", f"/api/structured-memory/ledger/{quote(key)}/append", entry)

    async def get_ledger_balance(self, key: str) -> LedgerBalanceResponse:
        return await self._request("GET", f"/api/structured-memory/ledger/{quote(key)}/balance")

    async def transition_state(self, key: str, request: StateTransitionRequest) -> StateTransitionResponse:
        return await self._request("POST", f"/api/structured-memory/state/{quote(key)}/transition", request)

    async def get_current_state(self, key: str) -> StateCurrentResponse:
        return await self._request("GET", f"/api/structured-memory/state/{quote(key)}/current")

    async def update_preference(self, key: str, request: PreferenceUpdateRequest) -> PreferenceUpdateResponse:
        return await self._request("POST", f"/api/structured-memory/preference/{quote(key)}/update", request)

    async def add_tree_child(self, key: str, request: TreeAddChildRequest) -> TreeAddChildResponse:
        return await self._request("POST", f"/api/structured-memory/tree/{quote(key)}/add-child", request)

    async def execute_query(self, query: str, group_id: str | None = None) -> MinnsQLResponse:
        return await self._request("POST", "/api/query", strip_none({"query": query, "group_id": group_id}))

    async def create_subscription(self, query: str, group_id: str | None = None) -> SubscriptionCreateResponse:
        return await self._request("POST", "/api/subscriptions", strip_none({"query": query, "group_id": group_id}))

    async def list_subscriptions(self) -> SubscriptionListResponse:
        return await self._request("GET", "/api/subscriptions")

    async def poll_subscription(self, subscription_id: str | int) -> SubscriptionPollResponse:
        return await self._request("GET", f"/api/subscriptions/{subscription_id}/poll")

    async def delete_subscription(self, subscription_id: str | int) -> SubscriptionDeleteResponse:
        return await self._request("DELETE", f"/api/subscriptions/{subscription_id}")

    async def create_table(self, request: TableCreateRequest) -> TableCreateResponse:
        return await self._request("POST", "/api/tables", request)

    async def list_tables(self) -> List[TableSchema]:
        return await self._request("GET", "/api/tables")

    async def get_table_schema(self, name: str) -> TableSchema:
        return await self._request("GET", f"/api/tables/{quote(name)}/schema")

    async def drop_table(self, name: str) -> TableDropResponse:
        return await self._request("DELETE", f"/api/tables/{quote(name)}")

    async def insert_rows(self, table: str, rows: TableRowInsertRequest | List[TableRowInsertRequest]) -> TableRowInsertResponse | List[TableRowInsertResponse]:
        return await self._request("POST", f"/api/tables/{quote(table)}/rows", rows)

    async def update_row(self, table: str, row_id: int, request: TableRowUpdateRequest) -> TableRowUpdateResponse:
        return await self._request("PUT", f"/api/tables/{quote(table)}/rows/{row_id}", request)

    async def delete_row(self, table: str, row_id: int) -> TableRowDeleteResponse:
        return await self._request("DELETE", f"/api/tables/{quote(table)}/rows/{row_id}")

    async def scan_rows(self, table: str, query: TableRowScanQuery | None = None) -> TableRowScanResponse:
        params: Dict[str, str] = {}
        if query:
            for k in ("when", "as_of", "group_id", "limit", "offset"):
                v = query.get(k)  # type: ignore[literal-required]
                if v is not None:
                    params[k] = str(v)
        qs = f"?{urlencode(params)}" if params else ""
        return await self._request("GET", f"/api/tables/{quote(table)}/rows{qs}")

    async def get_rows_by_node(self, table: str, node_id: int, group_id: int | None = None) -> TableRowScanResponse:
        qs = f"?group_id={group_id}" if group_id is not None else ""
        return await self._request("GET", f"/api/tables/{quote(table)}/by-node/{node_id}{qs}")

    async def compact_table(self, table: str) -> TableCompactResponse:
        return await self._request("POST", f"/api/tables/{quote(table)}/compact")

    async def get_table_stats(self, table: str) -> TableStatsResponse:
        return await self._request("GET", f"/api/tables/{quote(table)}/stats")

    async def create_workflow(self, request: WorkflowCreateRequest) -> WorkflowCreateResponse:
        return await self._request("POST", "/api/workflows", request)

    async def list_workflows(self, *, group_id: str | None = None, limit: int | None = None) -> WorkflowListResponse:
        params: Dict[str, str] = {}
        if group_id:
            params["group_id"] = group_id
        if limit is not None:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return await self._request("GET", f"/api/workflows{qs}")

    async def get_workflow(self, workflow_id: str | int) -> WorkflowDetailResponse:
        return await self._request("GET", f"/api/workflows/{workflow_id}")

    async def update_workflow(self, workflow_id: str | int, request: WorkflowUpdateRequest) -> WorkflowUpdateResponse:
        return await self._request("PUT", f"/api/workflows/{workflow_id}", request)

    async def delete_workflow(self, workflow_id: str | int) -> WorkflowDeleteResponse:
        return await self._request("DELETE", f"/api/workflows/{workflow_id}")

    async def transition_workflow_step(self, workflow_id: str | int, step_id: str, request: WorkflowStepTransitionRequest) -> WorkflowStepTransitionResponse:
        return await self._request("POST", f"/api/workflows/{workflow_id}/steps/{quote(step_id)}/transition", request)

    async def add_workflow_feedback(self, workflow_id: str | int, request: WorkflowFeedbackRequest) -> WorkflowFeedbackResponse:
        return await self._request("POST", f"/api/workflows/{workflow_id}/feedback", request)

    async def register_agent(self, request: AgentRegisterRequest) -> AgentRegisterResponse:
        return await self._request("POST", "/api/agents/register", request)

    async def list_agents(self, group_id: str) -> AgentListResponse:
        return await self._request("GET", f"/api/agents?{urlencode({'group_id': group_id})}")

    async def get_ontology_properties(self) -> OntologyPropertiesResponse:
        return await self._request("GET", "/api/ontology/properties")

    async def upload_ontology(self, ttl: str) -> OntologyUploadResponse:
        return await self._request("POST", "/api/ontology/upload", {"ttl": ttl})

    async def discover_ontology(self) -> OntologyDiscoverResponse:
        return await self._request("POST", "/api/ontology/discover")

    async def infer_ontology_cascades(self) -> OntologyCascadeInferenceResponse:
        return await self._request("POST", "/api/ontology/cascade-inference")

    async def get_ontology_observations(self) -> OntologyObservationsResponse:
        return await self._request("GET", "/api/ontology/observations")

    async def get_ontology_proposals(self) -> OntologyProposalsResponse:
        return await self._request("GET", "/api/ontology/proposals")

    async def get_ontology_proposal(self, proposal_id: str | int) -> OntologyProposal:
        return await self._request("GET", f"/api/ontology/proposals/{proposal_id}")

    async def approve_ontology_proposal(self, proposal_id: str | int) -> OntologyProposalApproveResponse:
        return await self._request("POST", f"/api/ontology/proposals/{proposal_id}/approve")

    async def reject_ontology_proposal(self, proposal_id: str | int) -> OntologyProposalRejectResponse:
        return await self._request("POST", f"/api/ontology/proposals/{proposal_id}/reject")

    async def get_ontology_stats(self) -> OntologyStatsResponse:
        return await self._request("GET", "/api/ontology/stats")

    async def upload_module(self, request: ModuleUploadRequest) -> ModuleUploadResponse:
        return await self._request("POST", "/api/modules", request)

    async def list_modules(self) -> List[ModuleInfo]:
        return await self._request("GET", "/api/modules")

    async def get_module(self, name: str) -> ModuleDetailResponse:
        return await self._request("GET", f"/api/modules/{quote(name)}")

    async def delete_module(self, name: str) -> ModuleDeleteResponse:
        return await self._request("DELETE", f"/api/modules/{quote(name)}")

    async def call_module_function(self, module_name: str, function_name: str, args_base64: str | None = None) -> ModuleCallResponse:
        body = {"args_base64": args_base64} if args_base64 else None
        return await self._request("POST", f"/api/modules/{quote(module_name)}/call/{quote(function_name)}", body)

    async def enable_module(self, name: str) -> None:
        await self._request("PUT", f"/api/modules/{quote(name)}/enable")

    async def disable_module(self, name: str) -> None:
        await self._request("PUT", f"/api/modules/{quote(name)}/disable")

    async def get_module_usage(self, name: str) -> ModuleUsageResponse:
        return await self._request("GET", f"/api/modules/{quote(name)}/usage")

    async def reset_module_usage(self, name: str) -> ModuleUsageResetResponse:
        return await self._request("POST", f"/api/modules/{quote(name)}/usage/reset")

    async def list_module_schedules(self, name: str) -> List[ModuleSchedule]:
        return await self._request("GET", f"/api/modules/{quote(name)}/schedules")

    async def create_module_schedule(self, module_name: str, request: ModuleScheduleCreateRequest) -> ModuleScheduleCreateResponse:
        return await self._request("POST", f"/api/modules/{quote(module_name)}/schedules", request)

    async def delete_module_schedule(self, module_name: str, schedule_id: int) -> ModuleScheduleDeleteResponse:
        return await self._request("DELETE", f"/api/modules/{quote(module_name)}/schedules/{schedule_id}")

    async def generate_strategies(self, request: PlanningStrategiesRequest) -> PlanningStrategiesResponse:
        return await self._request("POST", "/api/planning/strategies", request)

    async def generate_actions(self, request: PlanningActionsRequest) -> PlanningActionsResponse:
        return await self._request("POST", "/api/planning/actions", request)

    async def create_plan(self, request: PlanningPlanRequest) -> PlanningPlanResponse:
        return await self._request("POST", "/api/planning/plan", request)

    async def plan(self, goal_description: str) -> PlanningPlanResponse:
        return await self.create_plan({"goal_description": goal_description, "goal_bucket_id": 0, "context_fingerprint": 0, "session_id": self._default_session_id or 0})

    async def start_execution(self, request: PlanningExecuteRequest) -> PlanningExecuteResponse:
        return await self._request("POST", "/api/planning/execute", request)

    async def validate_event(self, request: PlanningValidateRequest) -> PlanningValidateResponse:
        return await self._request("POST", "/api/planning/validate", request)

    async def get_world_model_stats(self) -> WorldModelStatsResponse:
        return await self._request("GET", "/api/world-model/stats")

    async def export_database(self) -> bytes:
        response = await self._http.post("/api/admin/export")
        if not response.is_success:
            raise MinnsError(f"Export failed with status {response.status_code}", response.status_code)
        return response.content

    async def import_database(self, data: bytes, mode: str = "replace") -> AdminImportResponse:
        response = await self._http.post(f"/api/admin/import?mode={mode}", content=data, headers={"Content-Type": "application/octet-stream"})
        if not response.is_success:
            raise MinnsError(f"Import failed with status {response.status_code}", response.status_code)
        return response.json()

    async def create_api_key(self, request: ApiKeyCreateRequest) -> ApiKeyCreateResponse:
        return await self._request("POST", "/api/keys", request)

    async def list_api_keys(self) -> List[ApiKeyInfo]:
        return await self._request("GET", "/api/keys")

    async def delete_api_key(self, name: str) -> ApiKeyDeleteResponse:
        return await self._request("DELETE", f"/api/keys/{quote(name)}")

    async def recall_context(self, agent_id: AgentId, context: EventContext, *, claims_query: str | None = None, memory_limit: int = 5, strategy_limit: int = 5) -> RecallContextResult:
        import asyncio
        start = time.monotonic()
        empty_claims: ClaimSearchResponse = {"groups": [], "ungrouped": [], "total_results": 0}

        async def _strats() -> list:
            try:
                return await self.get_agent_strategies(agent_id, strategy_limit)
            except Exception:
                return []

        async def _mems() -> list:
            try:
                return await self.get_context_memories(context, limit=memory_limit, agent_id=agent_id)
            except Exception:
                return []

        async def _claims() -> ClaimSearchResponse:
            if not claims_query:
                return empty_claims
            try:
                return await self.search_claims({"query_text": claims_query, "top_k": 5})
            except Exception:
                return empty_claims

        strategies, memories, claims_result = await asyncio.gather(_strats(), _mems(), _claims())
        flat_claims = [
            *[c for g in claims_result.get("groups", []) for c in g.get("claims", [])],
            *claims_result.get("ungrouped", []),
        ]
        return {"strategies": strategies, "memories": memories, "claims": flat_claims, "recall_ms": int((time.monotonic() - start) * 1000)}


# ============================================================================
# Factory
# ============================================================================


def create_client(
    api_key: str,
    *,
    agent_id: AgentId | None = None,
    session_id: SessionId | None = None,
    base_url: str = BASE_URL,
) -> MinnsClient:
    """Create a synchronous :class:`MinnsClient` (convenience factory)."""
    return MinnsClient(api_key, base_url=base_url, agent_id=agent_id, session_id=session_id)


def create_async_client(
    api_key: str,
    *,
    agent_id: AgentId | None = None,
    session_id: SessionId | None = None,
    base_url: str = BASE_URL,
) -> AsyncMinnsClient:
    """Create an asynchronous :class:`AsyncMinnsClient` (convenience factory)."""
    return AsyncMinnsClient(api_key, base_url=base_url, agent_id=agent_id, session_id=session_id)

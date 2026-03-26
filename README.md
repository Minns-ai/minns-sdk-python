# minns-sdk (Python)

Python SDK for [minns](https://minns.ai) — a graph-native memory engine that turns conversations into queryable knowledge. Send messages, ask questions in natural language, and index code. Built for LLM-powered applications.

```bash
pip install minns-sdk
```

```python
from minns import create_client
```

---

## Quick Start

```python
from minns import create_client

client = create_client("your-api-key")

# 1. Send messages as they arrive (real-time ingestion)
client.send_message({
    "role": "user",
    "content": "Alice: Paid €50 for lunch - split with Bob",
    "case_id": "trip_2024",
})

client.send_message({
    "role": "user",
    "content": "I'm moving to Lower Manhattan, NYC.",
    "case_id": "trip_2024",
})

# 2. Ask questions about the graph
answer = client.query("Who owes whom?")
# answer["answer"], answer["confidence"], answer["entities_resolved"]

# 3. Clean up
client.close()
```

### Async

```python
from minns import AsyncMinnsClient

async with AsyncMinnsClient(api_key="your-api-key") as client:
    await client.send_message({
        "role": "user",
        "content": "Alice: Paid €50 for lunch - split with Bob",
        "case_id": "trip_2024",
    })
    answer = await client.query("Who owes whom?")
```

---

## Core Endpoints

### Messages (Real-Time)

Send individual messages as they arrive. Each message is processed through the event pipeline immediately, then buffered for deferred LLM compaction. Compaction triggers automatically when the buffer reaches 6 messages or 30 seconds.

```python
res = client.send_message({
    "role": "user",
    "content": "Alice: Paid €50 for lunch - split with Bob",
    "case_id": "trip_expenses_2024",
    "session_id": "session_01",
})

# res["buffered"]    — True if compaction is still pending
# res["buffer_size"] — current buffer depth
# res["compaction"]  — non-None when compaction was triggered
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | `str` | yes | `"user"` or `"assistant"` |
| `content` | `str` | yes | Message text |
| `case_id` | `str` | no | Case identifier for entity resolution continuity; auto-generated if omitted |
| `session_id` | `str` | no | Session identifier; auto-generated if omitted |
| `include_assistant_facts` | `bool` | no | Extract facts from assistant messages too (default `False`) |

Use the same `case_id` across calls for stable entity resolution and automatic deduplication.

### Conversations (Bulk Ingestion)

Ingest multiple sessions at once with inline LLM compaction. Use this when you have a batch of historical conversations to process.

```python
result = client.ingest_conversations({
    "case_id": "trip_expenses_2024",
    "sessions": [
        {
            "session_id": "session_01",
            "topic": "Dinner expenses",
            "messages": [
                {"role": "user", "content": "Alice: Paid €179 for museum - split with Bob"},
                {"role": "user", "content": "Bob: Paid €107 for dinner - split among all"},
            ],
        },
        {
            "session_id": "session_02",
            "topic": "Moving plans",
            "messages": [
                {"role": "user", "content": "I'm moving to Lower Manhattan, NYC."},
                {"role": "user", "content": "Johnny Fisher works with Christopher Peterson."},
            ],
        },
    ],
})

# result["events_submitted"]            — number of events sent to the pipeline
# result["compaction"]["facts_extracted"] — structured facts extracted by LLM
# result["compaction"]["llm_success"]    — whether all LLM calls succeeded
# result["rolling_summary_started"]      — whether a rolling summary was initiated
```

**Incremental ingestion:** Use the same `case_id` across calls. The server preserves entity→ID mappings and deduplicates already-processed messages automatically.

```python
# Call 1: First batch
client.ingest_conversations({"case_id": "trip_2024", "sessions": [batch1]})

# Call 2: More messages arrive later (same case_id)
client.ingest_conversations({"case_id": "trip_2024", "sessions": [batch2]})
# Duplicate messages from batch1 are skipped automatically
```

**Fact categories written as graph edges:**

| Category | Edge Type | Example |
|----------|-----------|---------|
| `location` | `state:location` | `"I'm moving to NYC"` |
| `work` | `state:work` | `"I started a new job at Google"` |
| `financial` | `financial:payment` | `"Alice: Paid €50 for lunch"` |
| `relationship` | `relationship:*` | `"Johnny works with Christopher"` |
| `preference` | `preference:*` | `"I love fantasy novels"` |
| `routine` | `state:routine` | `"I take morning walks in Battery Park"` |

### Query (Natural Language Query)

Ask questions about the graph in plain English. The pipeline classifies intent, resolves entities, builds a graph query, and returns a human-readable answer.

```python
# Simple string shorthand
res = client.query("What are the neighbors of Alice?")

# With pagination and conversational follow-ups (up to 5 exchanges)
res = client.query({
    "question": "What happened after the login event?",
    "limit": 20,
    "session_id": 1,
})

# res["answer"]           — human-readable answer
# res["intent"]           — classified intent
# res["entities_resolved"] — resolved entity mentions
# res["confidence"]       — classification confidence
# res["explanation"]      — step-by-step reasoning
```

**Supported intents:** `FindNeighbors`, `FindPath`, `FilteredTraversal`, `Subgraph`, `TemporalChain`, `Ranking`, `SimilaritySearch`, `Aggregate`, `StructuredMemoryQuery`.

### Code Intelligence

Submit source files for AST analysis, code reviews, and search code entities in the graph.

```python
# Index a source file
client.send_code_file_event({
    "agent_id": 1,
    "agent_type": "code-indexer",
    "session_id": 1,
    "file_path": "src/auth/login.rs",
    "content": "pub fn authenticate(user: &str, pass: &str) -> Result<Token, AuthError> { ... }",
    "language": "rust",
    "repository": "my-app",
    "enable_ast": True,
    "enable_semantic": True,
})

# Submit a code review
client.send_code_review_event({
    "agent_id": 1,
    "agent_type": "code-reviewer",
    "session_id": 1,
    "review_id": "PR-123-review-1",
    "action": "comment",
    "body": "This function should handle the null case explicitly.",
    "file_path": "src/auth/login.rs",
    "line_range": (42, 50),
    "repository": "my-app",
})

# Search code entities
results = client.search_code({
    "name_pattern": "authenticate",
    "kind": "function",
    "language": "rust",
    "limit": 20,
})
# results["entities"] — list of CodeEntity dicts
```

---

## Client Configuration

```python
from minns import create_client, MinnsClient

# Simple — API key only (connects to https://minns.ai)
client = create_client("your-api-key")

# With default IDs for event builders
client = create_client("your-api-key", agent_id=1, session_id=42)

# Full configuration
client = MinnsClient(
    api_key="your-api-key",
    agent_id=1,
    session_id=42,
    debug=True,
    enable_semantic=True,
    timeout=30.0,
)
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_key` | `str` | **(required)** | API key for authentication. Sent as `Bearer` token. |
| `agent_id` | `int \| str` | — | Default agent ID applied to all event builders. |
| `session_id` | `int \| str` | — | Default session ID applied to all event builders. |
| `timeout` | `float` | `30.0` | Request timeout in seconds. |
| `headers` | `dict[str, str]` | `Content-Type: application/json` | Custom HTTP headers (merged with defaults). |
| `debug` | `bool` | `False` | Log all requests and responses to the console. |
| `enable_semantic` | `bool` | `False` | Enable semantic indexing on all events by default. |
| `enable_default_telemetry` | `bool` | `False` | Send telemetry to `/api/telemetry` (fire-and-forget). |
| `on_telemetry` | `Callable` | — | Custom telemetry callback. |
| `max_payload_size` | `int` | `1048576` | Maximum payload size in bytes (1MB). |
| `auto_batch` | `bool` | `False` | Buffer events and send in batches. |
| `batch_interval` | `float` | `0.1` | Max seconds before flushing the batch queue. |
| `batch_max_size` | `int` | `10` | Max events before forcing a flush. |
| `max_queue_size` | `int` | `1000` | Max local queue depth before enqueue throws. |

> **Note:** The base URL defaults to `https://minns.ai`. Override with `base_url`.

---

## Architecture

minns has a unified pipeline. All data — messages, conversations, and structured events — flows through the same graph engine:

```
Event → Graph Construction → Episode Detection → Memory Formation → Strategy Extraction
                                    |
                                    ├→ Reinforcement Learning (edge weights, Q-values)
                                    ├→ Claims Extraction (LLM-driven entity/fact extraction)
                                    └→ World Model Training
```

**`send_message()`** — single message, deferred compaction (real-time/streaming).
**`ingest_conversations()`** — bulk batch, inline compaction.
**`query()`** — query the graph in natural language.
**Code endpoints** — index source files and reviews into the graph.

Events (below) augment the same graph with explicit structured telemetry.

---

## Advanced

### EventBuilder (Fluent API)

Augment the graph with structured events when your application has explicit actions, observations, or tool calls to record.

Create a builder with `client.event(agent_type)`. When `agent_id` and `session_id` are set on the client, every builder inherits them automatically:

```python
# Uses client defaults — no config needed
builder = client.event("my-agent")

# Override per-event when needed
builder = client.event("my-agent", agent_id=9999, session_id=42)

# Enable semantic indexing for this event only
builder = client.event("my-agent", enable_semantic=True)
```

#### Event Type Methods

Each builder defines **one** event type. Calling a second replaces the first.

| Method | Description |
|--------|-------------|
| `.action(name, params)` | Define an Action event. |
| `.observation(obs_type, data, *, confidence=, source=)` | Define an Observation event. |
| `.context(text, context_type=)` | Define a Context event (for claim extraction). Default type: `"general"`. |
| `.communication(message_type, sender, recipient, content)` | Define a Communication event. |
| `.cognitive(process_type, input_data, output_data, reasoning_trace=)` | Define a Cognitive event. |
| `.learning(learning_event)` | Define a Learning event (feedback loop). |

#### Metadata & Submission

| Method | Description |
|--------|-------------|
| `.meta(key, value)` | Add a metadata key-value pair. |
| `.duration(ms)` | Set action duration in milliseconds. |
| `.semantic(enabled=)` | Enable/disable semantic indexing. |
| `.language(lang)` | Set language for Context events. |
| `.is_code(enabled=)` | Mark event as containing source code. |
| `.outcome(result)` | Set action outcome to Success. |
| `.failure(error, error_code=)` | Set action outcome to Failure. |
| `.partial(result, issues)` | Set action outcome to Partial. |
| `.retry(attempt, max_retries)` | Attach retry metadata. |
| `.state(variables)` | Add environment variables. |
| `.goal(text, priority=, progress=)` | Add an active goal. |
| `.caused_by(parent_id)` | Link to a parent event (causality). |
| `.build()` | Return the raw `Event` dict. |
| `.send()` | Build and send (waits for server response). |
| `.enqueue()` | Build and queue (returns `LocalAck` immediately). |

#### Examples

```python
# Action with outcome
client.event("my-agent") \
    .action("api_call", {"endpoint": "/users"}) \
    .meta("source", "user_request") \
    .duration(150) \
    .outcome({"status": 200, "count": 42}) \
    .send()

# Context event with semantic indexing
client.event("my-agent") \
    .context("I prefer action movies and usually go on Friday evenings", "user_preference") \
    .semantic(True) \
    .send()

# Learning feedback loop
client.event("learner") \
    .learning({"Outcome": {"query_id": "action-123", "success": True}}) \
    .send()

# Fire-and-forget
receipt = client.event("my-agent") \
    .observation("web_page", {"url": "https://example.com"}) \
    .enqueue()
```

### Learning Event Variants

```python
.learning({"MemoryRetrieved": {"query_id": "q1", "memory_ids": [101, 102]}})
.learning({"MemoryUsed": {"query_id": "q1", "memory_id": 101}})
.learning({"StrategyServed": {"query_id": "q1", "strategy_ids": [1, 2, 3]}})
.learning({"StrategyUsed": {"query_id": "q1", "strategy_id": 1}})
.learning({"Outcome": {"query_id": "q1", "success": True}})
.learning({"ClaimRetrieved": {"query_id": "q1", "claim_ids": [10, 11]}})
.learning({"ClaimUsed": {"query_id": "q1", "claim_id": 10}})
```

### Simple Events

Quick integration path — no builder required.

```python
client.send_simple_event({
    "agent_id": 1,
    "agent_type": "assistant",
    "session_id": 1,
    "action": "respond",
    "data": {"query": "hello", "tokens": 150},
    "success": True,
})
```

### Typed Event Shortcuts

#### State Changes

Track entity state transitions. The server auto-updates structured memory state machines.

```python
client.send_state_change_event({
    "agent_id": 1,
    "agent_type": "workflow-engine",
    "session_id": 1,
    "entity": "Order-123",
    "new_state": "shipped",
    "old_state": "processing",
    "trigger": "warehouse_confirmation",
})
```

#### Transactions

Track financial or quantity transactions. The server auto-appends to structured memory ledgers.

```python
client.send_transaction_event({
    "agent_id": 1,
    "agent_type": "payment-service",
    "session_id": 1,
    "from_entity": "Alice",
    "to_entity": "Bob",
    "amount": 25.0,
    "direction": "Credit",
    "description": "Payment for services",
})
```

> **Note:** Python uses `from_entity`/`to_entity` instead of `from`/`to` (reserved keyword). The SDK maps these to the correct wire format automatically.

### Batch Processing

```python
events = [
    client.event("agent").action("a", {}).build(),
    client.event("agent").action("b", {}).build(),
]

client.process_events(events, enable_semantic=True)

# Manual flush when using auto_batch mode
client.flush()
```

### Search

Unified search across the graph: **Keyword** (BM25), **Semantic** (embedding), or **Hybrid** mode.

```python
# String shorthand — defaults to Hybrid mode
results = client.search("memory consolidation")

# Full options
results = client.search({
    "query": "memory consolidation",
    "mode": "semantic",
    "limit": 20,
    "fusion_strategy": "RRF",
})
```

### Claims

Claims are atomic facts extracted from events via the NER → LLM → Embedding pipeline.

```python
claims = client.get_claims(limit=10, event_id=42)
claim = client.get_claim_by_id(123)

# Semantic search — returns grouped results by subject entity
results = client.search_claims({
    "query_text": "Who is the project manager?",
    "top_k": 3,
    "min_similarity": 0.75,
})

# Process pending claims to generate embeddings
client.process_embeddings(100)
```

### Memory API

Memories are long-term learned experiences: Episodic → Semantic → Schema.

```python
memories = client.get_agent_memories(1, limit=10)
context_memories = client.get_context_memories(
    event_context,
    limit=5,
    min_similarity=0.8,
)
```

### Strategy API

Strategies are learned behavioral patterns with playbooks, failure modes, and counterfactual analysis.

```python
strategies = client.get_agent_strategies(1, limit=5)
similar = client.get_similar_strategies({
    "goal_ids": [703385],
    "tool_names": ["search_docs"],
    "min_score": 0.3,
})
suggestions = client.get_action_suggestions(context_hash, last_action_node=node_id, limit=5)
```

### Structured Memory

```python
# Upsert a structured memory template (Ledger, StateMachine, PreferenceList, Tree)
client.upsert_structured_memory({"key": "alice_bob_ledger", "template": {...}})

# List, get, delete
keys = client.list_structured_memory("alice")
entry = client.get_structured_memory("alice_bob_ledger")
client.delete_structured_memory("alice_bob_ledger")

# Ledger operations
client.append_ledger_entry("alice_bob_ledger", {
    "amount": 50, "description": "Lunch", "direction": "Credit",
})
balance = client.get_ledger_balance("alice_bob_ledger")

# State machine operations
client.transition_state("order_123", {"new_state": "shipped", "trigger": "warehouse"})
state = client.get_current_state("order_123")

# Preference and tree operations
client.update_preference("alice_prefs", {"item": "fantasy", "rank": 1, "score": 0.9})
client.add_tree_child("org_tree", {"parent": "CEO", "child": "CTO"})
```

### MinnsQL (Structured Query)

Execute Cypher-inspired queries with temporal semantics across both graph and tables.

```python
# Graph pattern matching
res = client.execute_query(
    'MATCH (a:Person)-[r:location]->(b) RETURN a.name, b.name'
)
# res["columns"] — ["a.name", "b.name"]
# res["rows"]    — [["alice", "london"], ["bob", "berlin"]]
# res["stats"]   — {"nodes_scanned": ..., "edges_traversed": ..., "execution_time_ms": ...}

# Table query (column refs must be qualified with table name)
client.execute_query(
    'FROM orders WHERE orders.status = "shipped" RETURN orders.customer, orders.amount'
)

# Graph-to-table JOIN
client.execute_query(
    'MATCH (n:Person) JOIN orders ON orders.node = n RETURN n.name, orders.amount'
)

# Temporal — edges valid during a range
client.execute_query(
    'MATCH (a)-[r]->(b) WHEN "2024-01-01" TO "2024-06-01" RETURN a.name'
)

# DDL/DML — create tables, insert, update, delete
client.execute_query(
    'CREATE TABLE orders (id Int64 PRIMARY KEY, customer String NOT NULL, amount Float64)'
)
client.execute_query('INSERT INTO orders VALUES (1, "Alice", 99.99)')
client.execute_query('UPDATE orders SET status = "shipped" WHERE id = 1')
client.execute_query('DELETE FROM orders WHERE status = "cancelled"')

# Multi-tenant scoping
client.execute_query('FROM orders RETURN orders.id', group_id="tenant-1")
```

Supports: aggregation (`count`, `sum`, `avg`, `min`, `max`, `collect`), `GROUP BY`, `ORDER BY`, `LIMIT`, variable-length paths (`[*1..3]`), temporal clauses (`WHEN`, `AS OF`), Allen's interval algebra predicates (`overlap`, `precedes`, `meets`, `covers`), and time bucketing (`time_bucket`, `date_trunc`, `ago`).

### Reactive Subscriptions

Register live MinnsQL queries that receive incremental updates as the graph changes.

```python
# Create a subscription — returns initial result set
sub = client.create_subscription(
    'MATCH (a:Agent)-[e:KNOWS]->(b:Agent) RETURN a.name, b.name, e.weight'
)
# sub["subscription_id"] — unique ID
# sub["initial"]         — {"columns": [...], "rows": [...]}
# sub["strategy"]        — "incremental" or "full_rerun: <reason>"

# Poll for updates (inserts/deletes since last poll)
updates = client.poll_subscription(sub["subscription_id"])
for update in updates["updates"]:
    print("New rows:", update["inserts"])
    print("Removed rows:", update["deletes"])

# List all active subscriptions
all_subs = client.list_subscriptions()

# Unsubscribe
client.delete_subscription(sub["subscription_id"])
```

WebSocket streaming is also available server-side at `GET /api/subscriptions/ws` for real-time push.

### Temporal Tables

Bi-temporal relational tables with graph linking via `NodeRef` columns.

```python
# Create a table (REST API)
client.create_table({
    "name": "orders",
    "columns": [
        {"name": "id", "col_type": "Int64", "primary_key": True, "nullable": False},
        {"name": "customer", "col_type": "String", "nullable": False},
        {"name": "amount", "col_type": "Float64"},
        {"name": "node", "col_type": "NodeRef"},
    ],
})

# Or via MinnsQL
client.execute_query(
    'CREATE TABLE orders (id Int64 PRIMARY KEY, customer String NOT NULL, amount Float64, node NodeRef)'
)

# Insert rows (single or batch)
client.insert_rows("orders", {"values": [1, "Alice", 99.99, None]})
client.insert_rows("orders", [
    {"values": [2, "Bob", 50.00, None]},
    {"values": [3, "Charlie", 75.00, None]},
])

# Update (creates a new version, old version's valid_until is closed)
client.update_row("orders", 1, {"values": [1, "Alice Updated", 105.0, None]})

# Soft-delete (closes valid_until, row remains queryable via WHEN ALL)
client.delete_row("orders", 3)

# Scan rows with temporal filtering
active = client.scan_rows("orders")                                 # active rows
all_rows = client.scan_rows("orders", {"when": "all"})              # all versions
snapshot = client.scan_rows("orders", {"as_of": timestamp})         # point-in-time

# Rows linked to a graph node
linked = client.get_rows_by_node("orders", 42)

# List tables, get schema, stats, compaction
tables = client.list_tables()
schema = client.get_table_schema("orders")
stats = client.get_table_stats("orders")
client.compact_table("orders")  # reclaim space from old versions
client.drop_table("orders")
```

Column types: `String`, `Int64`, `Float64`, `Bool`, `Timestamp`, `Json`, `NodeRef`.

### Workflows

Multi-step workflows with dependency tracking, state transitions, and outcome feedback.

```python
# Create a workflow
wf = client.create_workflow({
    "name": "Deploy Pipeline",
    "intent": "deploy",
    "description": "Standard deployment workflow",
    "steps": [
        {"id": "build", "role": "ci", "task": "Build and test", "depends_on": [],
         "inputs": {"source_branch": "main"}, "outputs": {"build_artifact": ""}},
        {"id": "deploy", "role": "cd", "task": "Deploy to staging", "depends_on": ["build"],
         "inputs": {"build_artifact": ""}, "outputs": {"deploy_url": ""}},
    ],
    "group_id": "team-1",
})
# wf["workflow_id"], wf["step_node_ids"] — {"build": 43, "deploy": 44}

# List and get workflows
wf_list = client.list_workflows(group_id="team-1")
detail = client.get_workflow(wf["workflow_id"])

# Transition a step
client.transition_workflow_step(wf["workflow_id"], "build", {
    "state": "completed",
    "result": "Build succeeded",
})

# Attach outcome feedback
client.add_workflow_feedback(wf["workflow_id"], {
    "feedback": "Deployment completed with zero downtime",
    "outcome": "success",  # "success" | "partial" | "failure"
})

# Update or delete
client.update_workflow(wf["workflow_id"], {"name": "Deploy Pipeline v2", "steps": detail["steps"]})
client.delete_workflow(wf["workflow_id"])
```

### Agent Registry

Register agents and discover peers for multi-agent coordination.

```python
# Register an agent
reg = client.register_agent({
    "agent_id": "coder-agent-1",
    "group_id": "team-1",
    "repository": "backend",
    "capabilities": ["code", "test", "review"],
})

# List agents in a group
agents = client.list_agents("team-1")
# agents["agents"] — [{"node_id": ..., "agent_id": ..., "capabilities": ..., ...}]
```

### Ontology Evolution

Manage the OWL/RDFS ontology that drives edge behaviors. Supports auto-discovery from graph patterns and a proposal review workflow.

```python
# List registered properties
props = client.get_ontology_properties()

# Upload a Turtle ontology
client.upload_ontology(
    '@prefix : <http://minnsdb.dev/ontology/> .\n:lives_in a owl:FunctionalProperty .'
)

# Auto-discover from graph patterns
discovery = client.discover_ontology()
# discovery["proposal_ids"] — new proposals to review

# Review proposals
proposals = client.get_ontology_proposals()
client.approve_ontology_proposal(proposals["proposals"][0]["id"])
client.reject_ontology_proposal(proposals["proposals"][1]["id"])

# Other operations
client.infer_ontology_cascades()
obs = client.get_ontology_observations()
stats = client.get_ontology_stats()
```

### WASM Agent Modules

Upload and manage sandboxed WASM modules that execute within the server with explicit permissions.

```python
# Upload a module
mod = client.upload_module({
    "name": "order-processor",
    "wasm_base64": wasm_bytes_base64,
    "permissions": ["table:orders:read", "table:orders:write", "graph:query"],
})
# mod["functions"] — ["process_order", "reconcile"]

# Call a function (args/result are base64-encoded MessagePack)
result = client.call_module_function("order-processor", "process_order", args_base64)

# Enable/disable
client.disable_module("order-processor")
client.enable_module("order-processor")

# Usage metering
usage = client.get_module_usage("order-processor")
client.reset_module_usage("order-processor")  # billing period reset

# Cron schedules
client.create_module_schedule("order-processor", {
    "cron": "0 */5 * * * *",
    "function": "reconcile",
})
schedules = client.list_module_schedules("order-processor")
client.delete_module_schedule("order-processor", schedules[0]["schedule_id"])

# List, get, delete modules
modules = client.list_modules()
info = client.get_module("order-processor")
client.delete_module("order-processor")
```

### Graph Import (Bulk)

Load pre-structured knowledge directly into the graph. Concept nodes are deduplicated by name. This skips the LLM/NER pipeline — for fact extraction from text, use conversation ingestion instead.

```python
client.import_graph({
    "nodes": [
        {"name": "Nike", "type": "concept", "properties": {"concept_type": "brand", "confidence": 0.95}},
        {"name": "Just Do It", "type": "concept", "properties": {"concept_type": "campaign"}},
        {"name": "Air Max 90", "type": "concept", "properties": {"concept_type": "product"}},
        {"name": "18-35 Males", "type": "concept", "properties": {"concept_type": "audience"}},
        {"name": "Instagram", "type": "concept", "properties": {"concept_type": "channel"}},
    ],
    "edges": [
        {"source": "Nike", "target": "Just Do It", "type": "association", "label": "runs_campaign", "weight": 0.9, "confidence": 0.95},
        {"source": "Just Do It", "target": "Air Max 90", "type": "association", "label": "promotes"},
        {"source": "Just Do It", "target": "18-35 Males", "type": "association", "label": "targets_audience"},
        {"source": "Just Do It", "target": "Instagram", "type": "association", "label": "runs_on_channel"},
    ],
    "group_id": "tenant-1",  # optional multi-tenant scoping
})
# {"nodes_created": 5, "nodes_reused": 0, "edges_created": 4, "errors": []}
```

**Node types:** `concept` (default), `agent`, `event`, `context`, `goal`, `episode`, `memory`, `strategy`, `tool`, `result`, `claim`.

**Edge types:** `association` (default), `causality`, `temporal`, `contextual`, `interaction`, `goal_relation`, `communication`, `derived_from`, `supported_by`, `code_structure`, `about`.

Edges support `weight` (default 0.8), `confidence` (default 0.9), `valid_from`/`valid_until` for temporal validity, and arbitrary `properties`. Source/target reference node `name` within the batch or existing Concept nodes already in the graph.

Then query with MinnsQL:

```python
res = client.execute_query(
    'MATCH (n:Concept {name: "Nike"})-[e]->(b) RETURN b.name, type(e)'
)
```

### Analytics & Graph

```python
analytics = client.get_analytics()
communities = client.get_communities("louvain")
centrality = client.get_centrality()
ppr = client.get_personalized_page_rank(42, limit=10, min_score=0.01)
reachable = client.get_reachability(42, max_hops=5)
path = client.get_causal_path(42, 99)
graph = client.get_graph({"limit": 100})
traversal = client.traverse_graph({"start": "42", "max_depth": 3})
client.persist_graph()
```

### Planning & World Model

Requires `ENABLE_WORLD_MODEL=true` and/or `ENABLE_STRATEGY_GENERATION=true` server-side.

```python
plan = client.plan("Reduce API latency by 50%")
strategies = client.generate_strategies({...})
actions = client.generate_actions({...})
execution = client.start_execution({...})
validation = client.validate_event({
    "execution_id": execution["execution_id"],
    "event": action_event,
})
wm_stats = client.get_world_model_stats()
```

### PAL (Perceive-Act-Learn) Cycle

High-level helpers that combine multiple API calls. Uses the LLM sidecar for local intent parsing.

```python
# Parallel recall of strategies, memories, claims
recall = client.recall_context(
    agent_id=1,
    context=event_context,
    claims_query="user preferences",
)

# Full PAL cycle: recall → parse LLM output → emit events
result = client.perceive_act_learn(
    "my-agent", 1, 42,
    message="Find me a good Italian restaurant",
    model_output=llm_raw_output,
    spec=intent_spec,
    claims_query="restaurant preferences",
    context_variables={"location": "NYC"},
)
```

### LLM Sidecar Intent Parsing

Extract structured intents from LLM responses locally — no network round-trips.

```python
from minns import build_sidecar_instruction, extract_intent_and_response

# 1. Generate a prompt instruction block for your LLM
instruction = build_sidecar_instruction(intent_spec)

# 2. Append instruction to your system prompt, then call your LLM

# 3. Parse the LLM output locally
intent, assistant_response = extract_intent_and_response(
    llm_output, user_message, intent_spec,
)
```

### Admin

```python
data = client.export_database()           # Returns bytes
result = client.import_database(data, "merge")
```

### System & Health

```python
stats = client.get_stats()
health = client.health_check()
```

---

## Error Handling

All API errors raise `MinnsError` with structured fields:

```python
from minns import MinnsError

try:
    client.send_message({"role": "user", "content": "hello"})
except MinnsError as err:
    print(err.args[0])       # Human-readable error
    print(err.status_code)   # HTTP status code
    print(err.details)       # Optional server-provided details
```

---

## Complete API Reference

### Core Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `send_message(request)` | `MessageResponse` | Send a single message (real-time, deferred compaction). |
| `ingest_conversations(request)` | `ConversationIngestResponse` | Bulk ingest conversations (inline compaction). |
| `query(question)` | `NLQResponse` | Natural language query (string shorthand or full options). |
| `send_code_file_event(request)` | `ProcessEventResponse` | Submit source file for AST analysis + graph ingestion. |
| `send_code_review_event(request)` | `ProcessEventResponse` | Submit code review comment/approval/change request. |
| `search_code(request)` | `CodeSearchResponse` | Search code entities by name, kind, language, file path. |

### Event Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `event(agent_type, **kwargs)` | `EventBuilder` | Create a fluent event builder. |
| `process_event(event, **kwargs)` | `ProcessEventResponse` | Send a single event. |
| `process_events(events, **kwargs)` | `ProcessEventResponse` | Batch send events (auto-chunked). |
| `send_simple_event(request)` | `ProcessEventResponse` | Send a simplified event (quick integration). |
| `send_state_change_event(request)` | `ProcessEventResponse` | Send a typed state-change event. |
| `send_transaction_event(request)` | `ProcessEventResponse` | Send a typed transaction event. |
| `get_events(limit=)` | `list[Event]` | List recent events. |
| `flush(**kwargs)` | `None` | Flush the local batch buffer. |
| `close()` / `destroy()` | `None` | Flush pending events and release resources. |

### Query & Search Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `execute_query(query, group_id=)` | `MinnsQLResponse` | Execute a MinnsQL structured query. |
| `search(query)` | `SearchResponse` | Unified search (Keyword/Semantic/Hybrid). |
| `get_claims(**kwargs)` | `list[ClaimResponse]` | List active claims. |
| `get_claim_by_id(id)` | `ClaimResponse` | Get a single claim by ID. |
| `search_claims(request)` | `ClaimSearchResponse` | Semantic search over claims. |
| `process_embeddings(limit=)` | `EmbeddingsProcessResponse` | Generate embeddings for pending claims. |

### Memory & Strategy Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_agent_memories(agent_id, limit=)` | `list[MemoryResponse]` | Get memories for an agent. |
| `get_context_memories(context, **kwargs)` | `list[MemoryResponse]` | Find memories similar to a context. |
| `get_agent_strategies(agent_id, limit=)` | `list[StrategyResponse]` | Get strategies for an agent. |
| `get_similar_strategies(request)` | `list[SimilarStrategyResponse]` | Find strategies by similarity. |
| `get_action_suggestions(context_hash, **kwargs)` | `list` | Get best next action suggestions. |
| `get_episodes(limit=)` | `list[EpisodeResponse]` | Get detected episodes. |

### Structured Memory Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `upsert_structured_memory(request)` | `None` | Upsert a template. |
| `list_structured_memory(prefix=)` | `StructuredMemoryListResponse` | List keys. |
| `get_structured_memory(key)` | `StructuredMemoryGetResponse` | Get by key. |
| `delete_structured_memory(key)` | `StructuredMemoryDeleteResponse` | Delete by key. |
| `append_ledger_entry(key, entry)` | `LedgerAppendResponse` | Append to ledger. |
| `get_ledger_balance(key)` | `LedgerBalanceResponse` | Get ledger balance. |
| `transition_state(key, request)` | `StateTransitionResponse` | Transition state machine. |
| `get_current_state(key)` | `StateCurrentResponse` | Get current state. |
| `update_preference(key, request)` | `PreferenceUpdateResponse` | Update preference list. |
| `add_tree_child(key, request)` | `TreeAddChildResponse` | Add tree child. |

### Graph & Analytics Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_analytics()` | `AnalyticsResponse` | Graph analytics with learning metrics. |
| `get_communities(algorithm=)` | `CommunityDetectionResponse` | Community detection. |
| `get_centrality(limit=)` | `CentralityResponse` | Node centrality scores. |
| `get_personalized_page_rank(source_node_id, **kwargs)` | `PPRResponse` | Personalized PageRank. |
| `get_reachability(source, **kwargs)` | `ReachabilityResponse` | Temporal reachability. |
| `get_causal_path(source, target)` | `CausalPathResponse` | Causal path between nodes. |
| `get_index_stats()` | `list[IndexStatsResponse]` | Property index stats. |
| `get_graph(query=)` | `GraphResponse` | Graph structure. |
| `get_graph_by_context(query)` | `GraphResponse` | Context-anchored subgraph. |
| `query_graph_nodes(request)` | `GraphNodeQueryResponse` | Search nodes by properties. |
| `traverse_graph(query)` | `GraphTraverseResponse` | Traverse from a starting node. |
| `persist_graph()` | `GraphPersistResponse` | Flush graph to disk. |
| `import_graph(request)` | `GraphImportResponse` | Bulk import nodes and edges. |

### Planning Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `plan(goal_description)` | `PlanningPlanResponse` | Shorthand planning. |
| `create_plan(request)` | `PlanningPlanResponse` | Full planning pipeline. |
| `generate_strategies(request)` | `PlanningStrategiesResponse` | Generate strategy candidates. |
| `generate_actions(request)` | `PlanningActionsResponse` | Generate action candidates. |
| `start_execution(request)` | `PlanningExecuteResponse` | Start execution tracking. |
| `validate_event(request)` | `PlanningValidateResponse` | Validate against world model. |
| `get_world_model_stats()` | `WorldModelStatsResponse` | World model statistics. |

### Reactive Subscription Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `create_subscription(query, group_id=)` | `SubscriptionCreateResponse` | Create a live MinnsQL subscription. |
| `list_subscriptions()` | `SubscriptionListResponse` | List active subscriptions. |
| `poll_subscription(subscription_id)` | `SubscriptionPollResponse` | Poll for incremental updates. |
| `delete_subscription(subscription_id)` | `SubscriptionDeleteResponse` | Unsubscribe. |

### Temporal Table Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `create_table(request)` | `TableCreateResponse` | Create a bi-temporal table. |
| `list_tables()` | `list[TableSchema]` | List all tables. |
| `get_table_schema(name)` | `TableSchema` | Get table schema. |
| `drop_table(name)` | `TableDropResponse` | Drop a table. |
| `insert_rows(table, rows)` | `TableRowInsertResponse` | Insert rows (single or batch). |
| `update_row(table, row_id, request)` | `TableRowUpdateResponse` | Update a row (creates new version). |
| `delete_row(table, row_id)` | `TableRowDeleteResponse` | Soft-delete a row. |
| `scan_rows(table, query=)` | `TableRowScanResponse` | Scan rows with temporal filtering. |
| `get_rows_by_node(table, node_id, group_id=)` | `TableRowScanResponse` | Get rows linked to a graph node. |
| `compact_table(table)` | `TableCompactResponse` | Reclaim space from old versions. |
| `get_table_stats(table)` | `TableStatsResponse` | Table statistics. |

### Workflow Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `create_workflow(request)` | `WorkflowCreateResponse` | Create a multi-step workflow. |
| `list_workflows(**kwargs)` | `WorkflowListResponse` | List workflows. |
| `get_workflow(workflow_id)` | `WorkflowDetailResponse` | Get workflow details. |
| `update_workflow(workflow_id, request)` | `WorkflowUpdateResponse` | Update a workflow. |
| `delete_workflow(workflow_id)` | `WorkflowDeleteResponse` | Soft-delete a workflow. |
| `transition_workflow_step(workflow_id, step_id, request)` | `WorkflowStepTransitionResponse` | Transition a step. |
| `add_workflow_feedback(workflow_id, request)` | `WorkflowFeedbackResponse` | Attach outcome feedback. |

### Agent Registry Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `register_agent(request)` | `AgentRegisterResponse` | Register an agent. |
| `list_agents(group_id)` | `AgentListResponse` | List agents in a group. |

### Ontology Evolution Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_ontology_properties()` | `OntologyPropertiesResponse` | List ontology properties. |
| `upload_ontology(ttl)` | `OntologyUploadResponse` | Upload Turtle ontology. |
| `discover_ontology()` | `OntologyDiscoverResponse` | Auto-discover from graph patterns. |
| `infer_ontology_cascades()` | `OntologyCascadeInferenceResponse` | Run cascade inference. |
| `get_ontology_observations()` | `OntologyObservationsResponse` | List observed predicates. |
| `get_ontology_proposals()` | `OntologyProposalsResponse` | List evolution proposals. |
| `get_ontology_proposal(proposal_id)` | `OntologyProposal` | Get a specific proposal. |
| `approve_ontology_proposal(proposal_id)` | `OntologyProposalApproveResponse` | Approve a proposal. |
| `reject_ontology_proposal(proposal_id)` | `OntologyProposalRejectResponse` | Reject a proposal. |
| `get_ontology_stats()` | `OntologyStatsResponse` | Ontology statistics. |

### WASM Module Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `upload_module(request)` | `ModuleUploadResponse` | Upload a WASM module. |
| `list_modules()` | `list[ModuleInfo]` | List all modules. |
| `get_module(name)` | `ModuleDetailResponse` | Get module details. |
| `delete_module(name)` | `ModuleDeleteResponse` | Unload a module. |
| `call_module_function(module_name, function_name, args_base64=)` | `ModuleCallResponse` | Call a module function. |
| `enable_module(name)` | `None` | Enable a module. |
| `disable_module(name)` | `None` | Disable a module. |
| `get_module_usage(name)` | `ModuleUsageResponse` | Get usage statistics. |
| `reset_module_usage(name)` | `ModuleUsageResetResponse` | Reset usage counters. |
| `list_module_schedules(name)` | `list[ModuleSchedule]` | List cron schedules. |
| `create_module_schedule(module_name, request)` | `ModuleScheduleCreateResponse` | Create a cron schedule. |
| `delete_module_schedule(module_name, schedule_id)` | `ModuleScheduleDeleteResponse` | Delete a schedule. |

### Admin & System Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `export_database()` | `bytes` | Export entire database. |
| `import_database(data, mode=)` | `AdminImportResponse` | Import database. |
| `recall_context(agent_id, context, **kwargs)` | `RecallContextResult` | Parallel recall of strategies, memories, claims. |
| `perceive_act_learn(...)` | `PerceiveActLearnResult` | Full PAL cycle. |
| `health_check()` | `HealthResponse` | Check system health. |
| `get_stats()` | `StatsResponse` | System-wide statistics. |

---

## License

MIT

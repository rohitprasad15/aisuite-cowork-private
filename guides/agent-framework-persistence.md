# Agent Framework Persistence

This spec defines how aisuite should persist agent state, trace data, and large
artifacts. The design keeps local usage simple while leaving a clean path to
Postgres-backed servers and a managed observability product.

## Goals

- Support local-first development with files and JSONL.
- Support crash recovery and resume on another server.
- Keep model-call continuation fast and reliable.
- Keep observability append-friendly and queryable.
- Keep large payloads out of hot state rows and trace indexes.
- Preserve the simple `Agent` + `Runner.run_sync(...)` path for novices.

## Non-Goals

- Persistence should not be mandatory for simple runs.
- Trace storage should not be required for continuation.
- State storage should not be optimized for analytics queries.
- Artifact storage should not decide what goes into model context.

## Store Types

aisuite should separate three persistence concerns:

```text
StateStore       hot path, resumability, correctness
TraceStore       observability, audit, read models
ArtifactStore    large payloads, lazy retrieval, shared references
```

The stores can share one database later, but they should remain separate
contracts.

## Identifiers

Use distinct identifiers for distinct jobs:

- `trace_id`: one runner invocation.
- `parent_run_id`: parent trace id when a subagent/tool creates a child run.
- `group_id`: related runs in the same task, session, or conversation.
- `thread_id`: resumable conversation or workflow state.
- `state_revision`: optimistic concurrency version for a stored state.
- `artifact_id`: addressable large payload.

`trace_id` is for observability. `thread_id` is for continuation. They can be
linked through metadata and `group_id`, but they should not be treated as the
same concept.

## StateStore

`StateStore` is the critical-path store for resume. It must be fast, compact,
and safe under concurrent workers.

It stores the latest continuation state needed to construct the next model
request:

- `thread_id`
- serialized `RunState`
- message history required for the next model call
- agent identity or application-level agent reference
- `group_id`
- metadata and tags needed for continuation
- pending tool calls or pending approval state, when supported
- `state_revision`
- timestamps

The store should support optimistic concurrency so two servers do not continue
the same thread from the same old state.

Suggested API:

```python
class StateStore:
    def save_state(
        self,
        thread_id: str,
        state: RunState,
        *,
        revision: int | None = None,
    ) -> StoredRunState:
        ...

    def load_state(self, thread_id: str) -> StoredRunState | None:
        ...

    def delete_state(self, thread_id: str) -> None:
        ...
```

Suggested stored wrapper:

```python
class StoredRunState:
    thread_id: str
    state: RunState
    revision: int
    created_at: str
    updated_at: str
    metadata: dict
```

### StateStore Requirements

- Writes should be atomic per `thread_id`.
- `save_state(..., revision=N)` should fail if the current revision is not `N`.
- State payloads should avoid unbounded tool outputs.
- State should refer to artifacts for large content when possible.
- Loading state should not require scanning trace events.

## TraceStore

`TraceStore` is the observability store. It records what happened and powers the
viewer, metrics, debugging, and future SaaS views. It is not the source of truth
for continuation.

It stores:

- raw trace events, append-only
- run summaries
- normalized activities
- parent/child run relationships
- token usage, latency, errors, approvals, and tool metadata

Suggested API:

```python
class TraceStore:
    def append_event(self, event: TraceEvent) -> None:
        ...

    def append_events(self, events: list[TraceEvent]) -> None:
        ...

    def list_runs(self, filters: RunFilters | None = None) -> list[RunRecord]:
        ...

    def get_run(self, trace_id: str) -> RunRecord | None:
        ...

    def list_events(self, trace_id: str) -> list[TraceEvent]:
        ...
```

`TraceStore` can be eventually consistent. A viewer lag of a second is
acceptable. Query APIs should return derived run/activity records rather than
making every UI client rebuild semantics from raw events.

### Raw Events and Read Models

Raw events are the source of truth:

- `run.started`
- `run.completed`
- `run.failed`
- `model.send`
- `model.response`
- `model.error`
- `tool.allowed`
- `tool.denied`
- `tool.started`
- `tool.completed`
- `tool.failed`

Read models are derived:

- run summary
- model call activity
- tool call activity
- generic event activity
- usage and latency summaries

The local viewer should consume the read model but still expose raw events for
debugging.

## ArtifactStore

`ArtifactStore` stores large or binary payloads that should not live inline in
state rows or trace indexes.

Examples:

- full shell stdout/stderr
- full tool results
- file contents before/after edits
- generated files
- screenshots and images
- uploaded attachments
- large provider raw payloads

Suggested API:

```python
class ArtifactStore:
    def put(
        self,
        data: bytes | str,
        *,
        media_type: str,
        metadata: dict | None = None,
    ) -> ArtifactRef:
        ...

    def get(self, ref: ArtifactRef) -> Artifact:
        ...

    def delete(self, ref: ArtifactRef) -> None:
        ...
```

Suggested reference:

```python
class ArtifactRef:
    artifact_id: str
    uri: str
    media_type: str
    size_bytes: int
    metadata: dict
```

Trace events and run state can both refer to artifacts:

```json
{
  "tool_name": "run_shell",
  "result_preview": "pytest failed...",
  "stdout_ref": "artifact://...",
  "stderr_ref": "artifact://..."
}
```

This keeps resume fast and UI payloads small while preserving full details for
on-demand retrieval.

## Message History and Large Tool Outputs

Continuation needs message history, but message history should not grow without
bound.

For each tool result, aisuite should be able to keep:

- compact content that is safe to feed back to the model
- artifact references for full content
- display previews for observability

The model-context representation and the audit representation do not need to be
identical. The harness should choose what enters model context; the stores
should preserve enough information for resume, audit, and UI retrieval.

## Local Implementations

Initial local-first implementations:

- `JsonlTraceStore`: append/read trace events from JSONL.
- `FileStateStore`: store latest `RunState` per `thread_id` as JSON.
- `FileArtifactStore`: store artifacts under a content-addressed or id-addressed
  local directory.

Suggested local layout:

```text
.aisuite/
  traces/
    events.jsonl
  state/
    <thread_id>.json
  artifacts/
    <artifact_id>
```

The local viewer should continue to support directly watching a JSONL trace
file. Internally, it can use `JsonlTraceStore`.

## Postgres and Managed Path

Future server implementations can use:

- Postgres for `StateStore`
- Postgres for `TraceStore` raw events and indexes
- local filesystem, S3, GCS, or another object store for `ArtifactStore`

Candidate Postgres tables:

```text
agent_states
  thread_id primary key
  revision
  state_json
  group_id
  metadata_json
  created_at
  updated_at

trace_events
  event_id primary key
  trace_id
  parent_run_id
  group_id
  event_type
  timestamp
  agent_name
  run_name
  tags_json
  metadata_json
  data_json

trace_runs
  trace_id primary key
  parent_run_id
  group_id
  run_name
  agent_name
  status
  started_at
  ended_at
  usage_json
  latency_json
  metadata_json

trace_activities
  activity_id primary key
  trace_id
  activity_type
  status
  started_at
  ended_at
  duration_ms
  tool_name
  model
  data_json
```

Useful indexes:

- `trace_events(trace_id, timestamp)`
- `trace_events(group_id, timestamp)`
- `trace_runs(group_id, started_at)`
- `trace_runs(parent_run_id)`
- `trace_activities(trace_id, started_at)`
- `agent_states(thread_id)`

Postgres can compute read models on write, on read, or asynchronously. The first
implementation should favor correctness and simplicity over premature
optimization.

## Runner Integration

Runner integration should stay optional:

```python
result = ai.Runner.run_sync(
    agent,
    "Start task",
    trace_sinks=[ai.tracing.LocalTraceSink(".aisuite/traces/events.jsonl")],
)
```

State persistence is explicit on the runner:

```python
result = ai.Runner.run_sync(
    agent,
    "Start task",
    thread_id="thread_123",
    state_store=state_store,
)
```

Persisted continuation uses the same `continue_sync` concept as in-memory
continuation. The state source changes from a `RunResult` to `state_store +
thread_id`:

```python
result = ai.Runner.continue_sync(
    agent,
    "Continue",
    thread_id="thread_123",
    state_store=state_store,
)
```

The key rule is that state persistence should not require trace persistence.

## Security and Retention

All stores can contain sensitive data:

- user prompts
- model responses
- tool inputs and outputs
- shell output
- file contents
- provider metadata

Applications should be able to configure:

- retention policy
- redaction hooks
- artifact size limits
- trace event filtering
- encryption at rest in server deployments

The default local implementation should be transparent: files under `.aisuite/`
should be treated as local development artifacts and should not be committed.

## Implementation Order

1. Add `TraceStore` interface and `JsonlTraceStore`.
2. Refactor the viewer to consume `JsonlTraceStore`.
3. Add tests for append, import, list runs, parent/child runs, and activities.
4. Add `FileStateStore` around `RunState`.
5. Add optimistic revision tests for `FileStateStore`.
6. Add `FileArtifactStore`.
7. Add optional artifact references for large shell/tool outputs.
8. Design and implement Postgres stores once local contracts are stable.

# StateStore API

`StateStore` is aisuite's persistence boundary for resumable agent runs. It is
separate from tracing: traces explain what happened, while state is the compact
source of truth needed to continue a thread after a crash, process restart, or
handoff to another server.

## Concepts

- `thread_id`: the stable application id for a resumable conversation or task.
- `RunState`: the serialized continuation payload produced by `RunResult.to_state()`.
- `revision`: an optimistic concurrency version for the stored thread state.
- `StoredRunState`: a wrapper around `RunState` that includes `thread_id`,
  `revision`, timestamps, and store-level metadata.

`thread_id` is intentionally not the same as `trace_id`. A trace id describes one
runner invocation. A thread id describes the resumable workflow that may span many
runner invocations.

## API

```python
class StateStore:
    def save_state(
        self,
        thread_id: str,
        state: RunState,
        *,
        revision: int | None = None,
        metadata: dict | None = None,
    ) -> StoredRunState:
        ...

    def load_state(self, thread_id: str) -> StoredRunState | None:
        ...

    def delete_state(self, thread_id: str) -> None:
        ...
```

### `save_state(...)`

Stores the latest `RunState` for a `thread_id` and returns a `StoredRunState`.

If `revision` is omitted, the store writes unconditionally. If `revision` is
provided, the write succeeds only when the currently stored revision matches.
This prevents two workers from both continuing the same old state.

```python
store = ai.FileStateStore(".aisuite/state")

result = ai.Runner.run_sync(agent, "Start the task")
stored = store.save_state("thread_123", result.to_state())

next_state = stored.state
next_state.add_user_message("Continue")
stored = store.save_state(
    stored.thread_id,
    next_state,
    revision=stored.revision,
)
```

A stale write raises `StateConflictError`:

```python
try:
    store.save_state("thread_123", next_state, revision=old_revision)
except ai.StateConflictError:
    latest = store.load_state("thread_123")
```

### `load_state(thread_id)`

Loads the latest state for a thread. This is the hot-path operation for resume.
It should not scan trace events.

```python
stored = store.load_state("thread_123")
if stored is not None:
    result = ai.Runner.run_sync(agent, stored.state)
```

### `delete_state(thread_id)`

Deletes stored continuation state. Deleting a missing thread is a no-op.

## StoredRunState Shape

```python
@dataclass
class StoredRunState:
    thread_id: str
    state: RunState
    revision: int
    created_at: str
    updated_at: str
    metadata: dict
```

`metadata` belongs to the stored thread record, not to model context. Use it for
application lookup fields such as `user_id`, `tenant_id`, `request_id`, or an
external task id. Agent/run metadata that should travel with the next model call
belongs inside `RunState.metadata`.

## Implementations

Current local implementations:

- `ai.InMemoryStateStore()`: useful for tests and notebooks.
- `ai.FileStateStore(root=".aisuite/state")`: stores one JSON file per `thread_id`.

`FileStateStore` writes through a temporary file and `os.replace(...)`, so each
save is atomic at the file level. It URL-encodes `thread_id` into the filename so
ids like `user/123:task` are safe on disk.

Future implementations can add Postgres or another server store behind the same
protocol. Those backends should preserve the same optimistic concurrency behavior.


## Postgres Design Direction

For Postgres, avoid making message order depend on `max(seq) + 1` as the main
semantic model. It can be made safe with locks and transactions, but it is less
flexible for cancellation, branching, and resume-from-an-earlier-point workflows.

The preferred shape is immutable message rows plus a mutable thread head that
stores the ordered ids used for the next model call:

```sql
agent_thread_heads (
  thread_id text primary key,
  model_context_message_ids text[] not null,
  full_history_message_ids text[] not null,
  step_ids text[] not null default '{}',
  compacted_from_message_ids text[] not null default '{}',
  state jsonb not null default '{}',
  revision bigint not null,
  metadata jsonb not null default '{}',
  created_at timestamptz not null,
  updated_at timestamptz not null
)

agent_messages (
  message_id text primary key,
  thread_id text not null,
  role text,
  message jsonb not null,
  artifact_refs jsonb not null default '[]',
  created_at timestamptz not null
)
```

Ordering is maintained by `model_context_message_ids`, not by message row ids or
timestamps. Loading model context means reading those ids in array order and
joining to `agent_messages`.

```sql
select m.message
from agent_thread_heads h
join unnest(h.model_context_message_ids) with ordinality as ids(message_id, ord)
  on true
join agent_messages m
  on m.message_id = ids.message_id
where h.thread_id = $1
order by ids.ord;
```

### Model Context vs Full History

Compaction makes this distinction important. After compaction, the model may only
need one or two messages, such as a summary message plus the latest user request.
In that case `model_context_message_ids` should shrink to the compacted context.

The UI still needs continuity. It should not lose the original turn-by-turn
conversation just because model context was compacted. Keep full user-visible
history separately from compact model context:

- `full_history_message_ids`: the complete ordered user-visible history for the
  thread. This is the UI continuity path.
- `model_context_message_ids`: the compact ordered messages to send to the model.
  After compaction this may be only a summary message plus recent messages.
- `compacted_from_message_ids`: ids that were summarized into the current compacted
  model-context message.
- `agent_compactions`: first-class compaction records that explain when and how
  a set of messages became a compact summary message.

`agent_compactions` is required for Postgres-backed state. Compaction is a
semantic transformation, not just a storage optimization. The store must preserve
which messages were compacted and what summary was produced so the model can
resume from compact context while the UI can still explain continuity.

```sql
agent_compactions (
  compaction_id text primary key,
  thread_id text not null,
  source_message_ids text[] not null,
  summary_message_id text not null,
  summary_text text not null,
  reason text,
  model text,
  input_token_count bigint,
  output_token_count bigint,
  created_at timestamptz not null,
  metadata jsonb not null default '{}'
)
```

`summary_message_id` must also exist in `agent_messages`. That message is the
actual compact reference that can be placed into `model_context_message_ids` and
fed to the next model call. `summary_text` is duplicated on the compaction record
for simple auditing and UI display; the canonical model-context message remains
the row in `agent_messages`.

Example after compacting messages `m1` through `m4`:

```text
full_history_message_ids:   [m1, m2, m3, m4, m5, m6]
agent_compactions:          c1 source=[m1, m2, m3, m4] summary=m_summary_1
model_context_message_ids:  [m_summary_1, m5, m6]
```

This gives two different read paths:

- Resume path: load `model_context_message_ids`, reconstruct compact context, call
  the model quickly.
- UI path: load `full_history_message_ids`, render the user-visible conversation,
  and show compaction boundaries when useful.

### Why Ordered Id Arrays

Ordered message-id arrays let the thread head represent the current semantic
view of the conversation:

- cancel the last model/user/tool message by removing ids from the head;
- resume from an older point by setting the model-context ids to a prefix;
- branch by creating another thread head with copied or prefixed ids;
- compact by replacing many model-context ids with a summary message id;
- show compaction boundaries in the UI without losing full history;
- keep immutable message rows for audit and UI reconstruction.

Writes still need optimistic concurrency. Update the thread head with
`where revision = $expected_revision`, append immutable message rows in the same
transaction, then bump `revision`.

Implementation sequence for aisuite:

`PostgresStateStore.from_dsn(...)` requires `psycopg`. Install it with
`pip install "aisuite[postgres]"`. Callers can also pass an existing
DB-API/psycopg connection to `PostgresStateStore(connection)`.

1. Add `PostgresStateStore` behind the existing `StateStore` API.
2. Store model-context messages as immutable rows and ordered ids on the thread
   head.
3. Store full-history ids separately from model-context ids.
4. Add compaction records and APIs that replace model-context ids with a summary
   message while leaving full-history ids intact.
5. Validate with unit tests for ordering/revision/compaction and integration tests
   against a real Postgres database before declaring the backend production-ready.

## ArtifactStore API

`ArtifactStore` stores large payloads that should not live inline in hot state
rows or trace indexes. For now, artifacts are a storage mechanism, not a context
optimization mechanism.

The core invariant is:

```text
artifactized message history -> hydrated message history -> model call
```

State and trace records can keep compact previews plus `ArtifactRef` values for
full content, but before aisuite calls the model it must hydrate message history
from the artifact store so the model sees the full content it would have seen if
the payload had remained inline. Later context optimization can choose to pass
previews or summaries, but that must be an explicit policy.

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

    def get(self, ref: ArtifactRef | str) -> Artifact:
        ...

    def delete(self, ref: ArtifactRef | str) -> None:
        ...
```

Current implementations:

- `ai.InMemoryArtifactStore()`: useful for tests and notebooks.
- `ai.FileArtifactStore(root=".aisuite/artifacts")`: stores one local directory per
  artifact with `data` and `metadata.json`.

`ArtifactRef` contains `artifact_id`, `uri`, `media_type`, `size_bytes`, and
metadata. The default metadata includes a `sha256` checksum.

## Design Rules

- State is for continuation, not analytics.
- Trace data is not required to resume a thread.
- State should stay compact enough for the next model call.
- Large outputs should eventually move to `ArtifactStore` and be referenced from
  state by id.
- Always pass `revision=stored.revision` when continuing state from a loaded
  record in a multi-worker/server environment.

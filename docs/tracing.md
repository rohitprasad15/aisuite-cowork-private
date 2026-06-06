# Tracing, stores, and the local viewer

The local observability path is intentionally store-backed:

```text
Agent run emits TraceEvent
        |
        v
TraceSink receives the event
        |
        v
TraceStore persists/query events and reconstructed runs
        |
        v
Viewer API reads from TraceStore
        |
        v
React UI renders runs, activities, artifacts, and subagents
```

## TraceSink

A `TraceSink` is the write side. The runner calls `sink.emit(event)` as a run progresses.

Current sinks:

- `LocalTraceSink(path)`: writes events to a JSONL-backed `JsonlTraceStore`.
- `HttpTraceSink(endpoint)`: posts event JSON to a viewer or collector HTTP endpoint.
- `TraceStoreSink(store)`: writes directly into any `TraceStore` implementation.
- `InMemoryTraceSink()`: stores `TraceEvent` objects in memory for tests and inspection.

Use a sink when code is producing trace events.

## TraceStore

A `TraceStore` is the read/write storage contract used by the viewer and store-backed sinks.

Required methods:

- `append_event(event)` / `append_events(events)`: write `TraceEvent` objects.
- `append_record(record)` / `append_records(records)`: write serialized trace records.
- `import_jsonl(content)`: import JSONL records.
- `list_records()`: return stored serialized records.
- `list_runs()`: return reconstructed run dictionaries.
- `get_run(trace_id)`: return one reconstructed run.
- `list_events(trace_id)`: return raw event records for one run.

Current stores:

- `JsonlTraceStore(path)`: local OSS default and CLI trace file storage.
- `InMemoryTraceStore(records=None)`: tests, notebooks, and embedded viewer usage.

Future stores can implement the same protocol, for example `PostgresTraceStore` or a hosted/SaaS-backed store.

## Viewer API

The viewer API is a thin HTTP layer over `TraceStore`:

- `GET /api/runs`: returns lightweight run summaries for navigation.
- `GET /api/runs/{trace_id}`: returns one sanitized run detail payload.
- `GET /api/events/{trace_id}`: returns raw trace events for a run.
- `POST /api/events`: appends one serialized trace event to the backing store.
- `POST /api/import-jsonl`: imports JSONL records into the backing store.
- `GET /api/artifacts/{artifact_id}`: retrieves artifact content from the configured `ArtifactStore`.

JSONL is one storage implementation, not the viewer contract. The UI and API should work the same way when the backing store is in-memory, JSONL, Postgres, or a future hosted store.

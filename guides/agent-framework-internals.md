# Agent Framework Internals

This note explains what happens when a developer calls `Runner.run_sync(...)`
and what trace data aisuite exports.

## Main Types

`Agent` is a declarative config object:

- `name`: logical agent name.
- `model`: provider-qualified model string, such as `openai:gpt-4o`.
- `instructions`: optional system instructions.
- `tools`: Python callables available to the model.
- `model_settings`: default model kwargs, such as temperature.
- `tags` and `metadata`: observability fields copied into runs and traces.

`Runner` is the execution engine. It owns message construction, client calls,
tool-loop setup, trace ids, trace events, and continuation.

`RunResult` is the public output. It includes the final output, messages,
new messages from the run, raw provider responses, observability fields, and
`steps`.

`RunState` is the serializable continuation format. `RunResult.to_state()`
captures messages, metadata, tags, and prior steps.

## Run Flow

At a high level, `Runner.run_sync(agent, input, ...)` does this:

1. Selects a client. If no client is provided, it creates `aisuite.Client()`.
2. Creates a new `trace_id`, unless tracing is disabled.
3. Builds messages from the input. If the agent has `instructions` and the
   input does not already start with a system message, the runner prepends one.
4. Merges tags and metadata from the agent, prior state, and run call.
5. Builds model kwargs from `agent.model_settings` and runtime overrides.
6. If tools are present, passes `tools` and `max_turns` into the chat call.
7. If a `tool_policy` is present, passes policy context with agent name,
   run name, trace id, parent run id, group id, tags, metadata, and messages.
8. Emits `run.started` and model/tool events to trace sinks when configured.
9. Calls `client.chat.completions.create(...)`.
10. Extracts the final output, response messages, raw responses, and run steps.
11. Emits `run.completed` with a full run snapshot.
12. Returns `RunResult`.

`Runner.run(...)` is currently an async wrapper around `run_sync(...)`.

## Continuation

`Runner.continue_sync(...)` supports two continuation sources.

`Runner.continue_sync(result, input, **overrides)` converts the previous
`RunResult` into `RunState`, appends the new user input, and calls
`Runner.run_sync(...)` with the last agent.

`Runner.continue_sync(agent, input, state_store=store, thread_id=...)` loads the
latest stored state, appends input, runs the agent, and saves the new state with
the loaded revision. This is the persisted continuation path for web servers,
workers, and interrupted runs that resume on another process.

Continuation keeps the prior messages. The new invocation gets a new
`trace_id`, while `group_id` can be reused to group all turns in the same
conversation or workflow.

## Subagents

`agent_tool(agent, ...)` exposes an `Agent` as a Python callable tool. When a
parent agent calls that tool, aisuite runs the subagent with the active client,
trace sinks, tool policy, tags, metadata, and group id.

The subagent run sets `parent_run_id` to the parent trace id, so viewers and
stores can connect parent and child runs.

## Run Steps

`RunResult.steps` is a list of span-like records. Each step has:

- `id`
- `type`
- `name`
- `trace_id`
- `parent_id`
- `started_at`
- `ended_at`
- `data`

Current step types are:

- `agent`: one step for the runner invocation.
- `model_response`: one step for each raw model response.
- `tool_call`: a tool request, allow/deny decision, or failed tool call.
- `tool_result`: a completed tool result.
- `handoff` and `custom`: reserved for future framework behavior.

## Trace Snapshots

`RunResult.trace_to_dict()` exports a JSON-serializable snapshot with:

- `trace_id`, `parent_run_id`, `group_id`, and `run_name`
- `agent_name` and `status`
- `tags` and `metadata`
- `final_output`
- `messages` and `new_items`
- `message_count` and `step_count`
- `steps`

`RunResult.write_trace_jsonl(path)` appends that snapshot as one JSON line.
This is the simplest export path when you only need completed run records.

## Trace Events

For live or incremental observability, configure trace sinks. Sinks receive
`TraceEvent` records with `record_type="trace_event"` and
`schema_version=TRACE_SCHEMA_VERSION`.

The current event types are:

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

Each event includes:

- `event_id`
- `event_type`
- `timestamp`
- `trace_id`
- `span_id` and `parent_span_id`
- `parent_run_id`
- `group_id`
- `run_name`
- `agent_name`
- `tags`
- `metadata`
- `data`

Available sinks:

- `InMemoryTraceSink`: useful for tests.
- `LocalTraceSink`: writes event JSONL to disk.
- `HttpTraceSink`: posts each event to an HTTP endpoint.

Use `ai.tracing.configure(...)` to set process-wide default sinks, or pass
`trace_sinks=[...]` to a single runner call.

## Trace Store and Viewer

`JsonlTraceStore` reads event JSONL and reconstructs runs. It keeps raw events
by trace id and uses the `run.completed` event's embedded run snapshot when it
is available.

The local viewer consumes the same store. It can show completed snapshot files
or event JSONL files, including parent/child run relationships via
`parent_run_id`.

## Sensitive Data Note

Trace snapshots and events can include messages, tool inputs, tool outputs,
metadata, and final output. Treat trace files as sensitive unless the calling
application has filtered the data before passing it into aisuite.

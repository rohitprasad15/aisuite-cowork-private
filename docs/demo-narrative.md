# aisuite agents demo narrative

## Positioning

The notebook is the **Agents API demo**. It should show the reusable core directly:

```python
agent = ai.Agent(...)
result = ai.Runner.run_sync(agent, "...")
```

The CLI is an **agent harness built on top of the Agents API**. `aisuite-code` is not the Agents API itself; it is a reference implementation that shows how to build a useful local coding harness with the API. For implementation guidance, see `guides/agent-harness-api.md`.

LangChain's [The Anatomy of an Agent Harness](https://www.langchain.com/blog/the-anatomy-of-an-agent-harness) frames this as `Agent = Model + Harness`: the model provides intelligence, while the harness is the system around it that makes the model useful. In that framing, a harness includes code, configuration, tools, execution logic, state, constraints, and environment management around the model.

For aisuite, this gives us a precise taxonomy:

- **Agents API**: the reusable core primitives: `Agent`, `Runner`, tools, state, tracing, policies, and stores.
- **Agent harness**: an opinionated runtime/application around an agent for a domain.
- **`aisuite-code`**: our first local coding agent harness, built on top of the Agents API.
- **Viewer**: local observability for runs, tool calls, artifacts, subagents, latency, and token usage.
- **Stores and sinks**: infrastructure adapters for state, traces, and artifacts.

This distinction gives aisuite a clean product story:

1. **Agents API**: clean primitives, novice-friendly, OpenAI-inspired, notebook-friendly, provider-agnostic.
2. **Local Harnesses**: `aisuite-code` as the first harness with tools, policies, local traces, artifacts, and subagents.
3. **Production Path**: same agents and runner, with durable stores and hosted observability added later.

## Core Message

Build locally, observe locally, deploy later, optionally use managed observability.

The developer can prototype in a notebook, move to a CLI when they need local tools and project files, observe every run locally, and later promote the same agent code to production with persistent state and managed observability.

## Demo Flow

### 1. Notebook Prototype

Start in a notebook because many AI developers naturally begin there. Create an `Agent`, attach tools, run it, and embed the local trace viewer directly in the notebook.

```python
viewer = ai.tracing.start_viewer(
    None,
    port=0,
    trace_store=ai.tracing.InMemoryTraceStore(),
)
result = ai.Runner.run_sync(
    agent,
    "Inspect this workspace",
    trace_sinks=[viewer.trace_sink],
)
```

The notebook can show either the full viewer or a focused single-run view:

```python
display(IFrame(
    f"{viewer.url}?embed=1&trace_id={result.trace_id}",
    width="100%",
    height=720,
))
```

### 2. Real Key Demo

The no-key scripted path is useful for deterministic UI demos, but the real-key path proves model and tool behavior.

With `OPENAI_API_KEY`, the model can list files, read content, call tools, and produce a final answer. The viewer shows the model request, model response, tool call, tool result, final output, and usage/latency where available.

### 3. Move To CLI

When the developer wants to work with a real local directory, move to `aisuite-code`:

```bash
./scripts/aisuite-code --cwd /tmp/aisuite-cli-play --viewer
```

The CLI is still just an aisuite agent harness. It combines the Agents API with the harness-level pieces needed for local coding: filesystem tools, shell tools, git tools, a reviewer subagent, approval policy, artifact storage, and local traces.

Example prompt:

```text
Create a small Python app with add(a, b), run it, and show git status.
```

Point out the permission prompt, compact tool activity, assistant answer, trace id, and focused viewer URL.

### 4. Local Observability

Every run is observable locally. The viewer can read from a JSONL file, an in-memory `TraceStore`, or eventually a database-backed `TraceStore`.

This gives developers a local LangSmith-like loop without requiring a hosted service:

- Multiple runs in the left navigation.
- Single run detail in focused mode.
- Tool timeline.
- Subagent runs.
- Artifact preview and on-demand artifact loading.
- Token and latency metadata when providers expose it.

### 5. Promotion Story

The production story is intentionally aligned with the local story. Users should not rewrite their agent to deploy it.

Local:

```python
Runner.run_sync(agent, input, trace_sinks=[viewer.trace_sink])
```

Production later:

```python
Runner.run_sync(
    agent,
    input,
    state_store=PostgresStateStore(...),
    trace_sinks=[ManagedTraceSink(...)],
)
```

The same agent, tools, runner, and policy hooks remain. Locally, traces go to JSONL or the local viewer. In production, state can go to Postgres, artifacts can go to an artifact store, and traces can go to a managed observability sink.

## Why This Matters

This creates three layers:

- A simple Agents API for novices.
- Harnesses that demonstrate serious local workflows without hiding the API.
- Serious hooks for production systems.
- Local observability from day one.

The CLI and notebook are the first two local-first entry points. The production store and hosted trace sink are natural extensions, not separate products.

## One-Line Close

aisuite lets developers build agents locally, observe them locally, and promote them later without changing the core programming model.

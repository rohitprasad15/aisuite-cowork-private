# Agent Framework Direction

This note records the intended product shape for aisuite's agent work. Future
changes should preserve the split between a simple Agent API and an optional
agent harness layer.

## Core Positioning

aisuite should be the cleanest path from an LLM call to a real agent app:

```text
Build locally, observe locally, deploy later, optionally use managed observability.
```

The basic user journey should stay small and obvious:

```python
agent = ai.Agent(
    name="assistant",
    model="openai:gpt-4o",
    instructions="Answer briefly.",
    tools=[my_tool],
)

result = ai.Runner.run_sync(agent, "Help me with this task.")
```

A new user should not need tracing, persistence, subagents, approval policies,
or stores before they can run an agent. Those capabilities should appear when
they are useful.

## Product Focus

The near-term product wedge is a strong local developer loop:

- `Agent` and `Runner` remain the simple programmable core.
- Standard toolkits make useful agents easy to assemble.
- `aisuite-code` demonstrates tools, approvals, artifacts, and subagents in a
  real workflow.
- The local viewer makes runs understandable without a hosted service.
- Stores provide the bridge from local files to Postgres and managed aisuite.

This gives a credible open-source path and a natural managed product path. A
developer can start in a notebook or CLI, inspect local traces, add state and
artifacts, deploy with Postgres, and later point the same trace/events model at
a hosted observability service.

## Agent API vs Harness

The Agent API includes the minimal abstractions:

- `Agent`: reusable agent definition.
- `Runner`: execution entry point.
- `RunResult`: output, messages, state, and trace identifiers.
- Tools: plain Python callables exposed to the model.

The harness layer adds operational behavior:

- Standard toolkits such as files, shell, and future web/git/browser tools.
- Tool security policy and interactive approvals.
- Trace events, normalized activities, tokens, latency, and viewer support.
- Persistence through stores such as JSONL now and Postgres later.
- Continuation/resume across turns or processes.
- Subagents as tools.
- CLI, notebook, local viewer, and future server/SaaS adapters.

The harness should be optional and composable. It should not make the first
agent example harder.

## Design Principles

1. Keep novice usage clean.
   The default path should be `Agent(...)` plus `Runner.run_sync(...)`.

2. Add power through optional parameters and helper modules.
   Advanced concepts should appear when the user asks for them: tracing,
   persistence, policies, standard toolkits, subagents, or CLI behavior.

3. Prefer explicit runtime contracts over hidden behavior.
   Tool execution, approval, model calls, trace events, continuation, and
   failure modes should have clear data shapes.

4. Keep raw data and read models separate.
   Raw trace events are the source of truth. Derived runs and activities are
   read models for UI, metrics, persistence, and APIs.

5. Avoid tying the agent API to one provider.
   The API may be inspired by OpenAI and Claude ergonomics, but it should remain
   provider-agnostic.

6. Make local-first work well.
   JSONL traces, the local viewer, and notebook usage should stay useful even if
   a future Postgres or managed service exists.

7. Treat tools as side-effect boundaries.
   Tools should carry metadata for risk, approval, capabilities, and display.
   The harness should make dangerous actions visible and controllable.

## What Not To Do

- Do not make the basic `Agent` constructor require harness concepts.
- Do not make persistence mandatory for simple runs.
- Do not hide tool execution or approvals inside opaque callbacks.
- Do not make the viewer invent observability semantics that the backend does
  not expose.
- Do not add broad abstractions unless they simplify a real user workflow.

## Current Direction

The near-term roadmap is:

1. Keep hardening the Agent API and `Runner`.
2. Make `aisuite-code` plus the local viewer the reference demo of the harness.
3. Improve viewer payloads, artifact display, and timeline scanability.
4. Expand standard toolkits for files, shell, web/search, git, and browser-like
   workflows.
5. Keep `TraceStore`, `StateStore`, and `ArtifactStore` as separate contracts so
   local, Postgres, and managed backends can evolve independently.
6. Add Postgres-backed production persistence once local store semantics are
   stable.

In short:

```text
Agent API = simple programmable core
Harness   = Agent API + tools + safety + state + observability + UX adapters
```

Both matter. The Agent API should remain approachable; the harness should make
real agent systems reliable, observable, and safe to operate.

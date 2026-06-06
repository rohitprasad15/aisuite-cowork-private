# Agent Harness API Guide

An agent harness is an application/runtime built on top of the aisuite Agents API. The Agents API supplies the reusable core: `Agent`, `Runner`, tools, policies, state, tracing, and stores. A harness chooses how those pieces become a user-facing workflow.

`aisuite-code` is the first reference harness in this repo. It is a local coding harness, not the framework itself.

## Harness Responsibilities

A useful harness owns these decisions:

- **Session loop**: how user input enters the agent and how continuations are handled.
- **Toolkits**: which tools are available for the domain, such as filesystem, shell, git, or subagent tools.
- **Policy**: which tool calls run automatically, which require approval, and how denials are handled.
- **State**: whether conversation state is in memory, file-backed, database-backed, or omitted for simple demos.
- **Artifacts**: where large tool inputs and outputs are stored and how previews are shown.
- **Tracing**: which `TraceSink` receives events and which `TraceStore` powers inspection.
- **User experience**: CLI, notebook, web app, service endpoint, or another interface.

## Minimal Harness Shape

```python
import aisuite as ai

agent = ai.Agent(
    name="local_assistant",
    model="openai:gpt-4o-mini",
    instructions="Help with local project tasks.",
    tools=[
        *ai.toolkits.files(root=".", allow_write=True),
        *ai.toolkits.shell(cwd=".", allowed_commands=["python3", "pytest"]),
    ],
    tags=["harness", "local"],
    metadata={"app": "my_harness"},
)

trace_sink = ai.tracing.LocalTraceSink(".aisuite/events.jsonl")
artifact_store = ai.FileArtifactStore(".aisuite/artifacts")

result = ai.Runner.run_sync(
    agent,
    "Inspect the project and run the focused tests.",
    trace_sinks=[trace_sink],
    artifact_store=artifact_store,
    run_name="local_turn",
    group_id="my-harness-session",
)

print(result.final_output)
```

## Adding Policy

A harness can pass a callable or policy object as `tool_policy`. The policy receives `ToolPolicyContext` and returns a decision.

```python
def approve_writes(context: ai.ToolPolicyContext) -> ai.ToolPolicyDecision:
    if context.tool_name in {"read_file", "list_files"}:
        return ai.ToolPolicyDecision(allowed=True, reason="low risk")
    return ai.ToolPolicyDecision(allowed=False, reason="requires UI approval")

result = ai.Runner.run_sync(
    agent,
    "Make a small edit.",
    tool_policy=approve_writes,
)
```

A CLI harness can turn that policy callback into an interactive approval prompt. A service harness can map it to organization policy or human approval workflows.

## Continuing A Session

A harness should use `Runner.continue_sync` when the user sends the next message in the same conversation.

```python
next_result = ai.Runner.continue_sync(
    result,
    "Now summarize what changed.",
    trace_sinks=[trace_sink],
    artifact_store=artifact_store,
)
```

For production-style resumability, use a `StateStore` and thread id. The harness chooses the store implementation.

```python
store = ai.FileStateStore()

first = ai.Runner.run_sync(
    agent,
    "Start the task.",
    state_store=store,
    thread_id="thread_123",
)

next_result = ai.Runner.continue_sync(
    agent,
    "Continue the task.",
    state_store=store,
    thread_id="thread_123",
)
```

## Wiring Observability

For local development, the harness can start the viewer and pass its sink into the runner.

```python
trace_store = ai.tracing.InMemoryTraceStore()
viewer = ai.tracing.start_viewer(None, port=0, trace_store=trace_store)

result = ai.Runner.run_sync(
    agent,
    "Do the work.",
    trace_sinks=[viewer.trace_sink],
)

print(f"Focused viewer: {viewer.url}?embed=1&trace_id={result.trace_id}")
```

For a CLI or long-running local process, a file-backed trace sink is often better:

```python
trace_sink = ai.tracing.LocalTraceSink(".aisuite/events.jsonl")
viewer = ai.tracing.start_viewer(".aisuite/events.jsonl", port=0)
```

The same harness shape can later replace local sinks/stores with hosted or database-backed implementations.

## Reference: aisuite-code

`aisuite-code` demonstrates these harness choices:

- Terminal session loop and `/help`, `/status`, `/last`, `/viewer` commands.
- File, shell, git, and reviewer subagent tools.
- Interactive approval prompts for risky tools.
- Local JSONL trace sink and file artifact store under `.aisuite/`.
- Local viewer integration and focused run links.

Use it as a reference for building domain-specific harnesses such as research, support, data analysis, or internal operations agents.

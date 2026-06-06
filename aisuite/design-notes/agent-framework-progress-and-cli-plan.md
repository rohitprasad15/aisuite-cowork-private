# Agent Framework Progress And CLI Plan

This note tracks implementation progress beyond the core Agent API spec and
lays out the next CLI milestone.

## Current Status

The branch now has a usable first pass of the aisuite agent framework:

- `Agent` declaratively defines model, instructions, tools, tags, and metadata.
- `Runner.run_sync(...)` and `Runner.continue_sync(...)` execute and continue
  runs.
- `RunResult` and `RunState` keep the state serializable and avoid a first-class
  session abstraction.
- Subagents can be exposed as tools with `ai.agent_tool(...)`.
- Tool calls support runtime policy checks through `tool_policy`.
- Trace events can be emitted to sinks and reconstructed through a store.
- The local viewer can inspect runs from JSONL trace data.
- The viewer direction is now split into durable JSONL file mode and optional
  live HTTP event ingestion, with a Vite UI replacing the embedded HTML path.

The public shape is intentionally simple:

```python
import aisuite as ai

agent = ai.Agent(
    name="coder",
    model="openai:gpt-4o",
    tools=[
        *ai.toolkits.files(root="."),
        *ai.toolkits.shell(cwd=".", allowed_commands=["pytest", "python3"]),
    ],
)

result = ai.Runner.run_sync(agent, "Read the tests and run them.")
```

## Observability Progress

The tracing path now has these layers:

- `TraceEvent`: structured event record with schema version, run identity, group
  identity, parent run identity, tags, metadata, and event data.
- `TraceSink`: emission interface.
- `LocalTraceSink`: writes JSONL events locally.
- `HttpTraceSink`: posts trace events to a local or remote collector endpoint.
- `InMemoryTraceSink`: useful for tests and embedded apps.
- `TraceStore`: read/query abstraction for future persistence backends.
- `JsonlTraceStore`: local implementation that reconstructs runs from JSONL.
- Viewer: local collector/API server plus Vite UI served from
  `python -m aisuite.agents.viewer`.

This gives us a path to Postgres later without making the current OSS/local path
heavy.

### Normalized Model Events

Model calls are emitted as normalized events:

- `model.send`: the request sent to the provider.
- `model.response`: the provider response.
- `model.error`: provider failure before a usable response.

The normalized payload keeps observability useful without making traces a raw
transcript by default. Text fields are represented as previews with
`text_preview`, `text_length`, `truncated`, and `content_redacted`. Multimodal
inputs report modalities such as `text` and `image`; responses report whether
the model produced text, tool calls, or both.

Tool-capable runs emit model events from the client/tool execution layer so the
timeline order matches what actually happened: model request, model response,
tool approval/execution, then the next model request.

## Tool Policy And Metadata

Plain Python function tools still work with no policy and no metadata.

Optional metadata can be attached:

```python
tool = ai.tool(
    run_shell,
    metadata=ai.ToolMetadata(
        category="shell",
        risk_level="high",
        capabilities=["run_command"],
        requires_approval=True,
    ),
)
```

Runtime policy remains an explicit hook:

```python
def approve(context: ai.ToolPolicyContext) -> ai.ToolPolicyDecision:
    approved = ask_user(
        f"Allow {context.tool_name} with {context.arguments}?"
    )
    return ai.ToolPolicyDecision(
        allowed=approved,
        reason="approved by user" if approved else "denied by user",
    )

result = ai.Runner.run_sync(
    agent,
    "Run the tests",
    tool_policy=ai.RequireApprovalPolicy(approve),
)
```

Built-in policies currently include:

- `AllowAllToolPolicy`
- `DenyAllToolPolicy`
- `AllowToolsPolicy`
- `RequireApprovalPolicy`

## Standard Toolkits

The first standard toolkits are implemented in `aisuite.toolkits`.

### File Toolkit

```python
ai.toolkits.files(root=".", allow_write=False)
```

Provides:

- `list_files`
- `read_file`
- `search_files`
- `write_file` when `allow_write=True`

Guardrails:

- all paths are scoped to `root`
- path traversal is blocked
- read/search byte limits are enforced
- writing is opt-in
- write metadata is medium risk and requires approval

### Shell Toolkit

```python
ai.toolkits.shell(
    cwd=".",
    allowed_commands=["pytest", "python3"],
)
```

Provides:

- `run_shell`

Guardrails:

- `allowed_commands` is required unless `allow_all=True`
- commands run in configured `cwd`
- `shell=False` by default
- timeout is enforced
- stdout, stderr, exit code, and timeout status are captured
- metadata marks the tool as high risk and approval-worthy

## Viewer UX Direction

The viewer is functional but still not product-grade. The target direction is:

- calm overview first
- grouped runs by `group_id`
- parent/child run navigation
- transcript, events, and raw JSON behind progressive disclosure
- tool calls show policy result, metadata, and arguments/results on demand
- visual tone closer to modern developer tools than dense enterprise dashboards

The static mock in `agent-runs-ui-mock.html` is the north star for polish. The
runtime viewer should continue moving toward that direction after the CLI
creates richer real-world traces.

## CLI Plan

The next major milestone is a simple developer CLI that demonstrates the
framework end to end. It lives outside the core package so we can later add
TypeScript CLIs without mixing implementation languages:

```text
cli/
  py/
    aisuite-code-cli/
  ts/
    # future TypeScript CLIs
```

The CLI should be modeled after Codex and Claude Code at the interaction level:

- terminal app
- conversation shown above
- input area at the bottom
- tool calls rendered inline in the conversation
- risky tool calls pause for user approval
- approvals use `RequireApprovalPolicy`
- traces stream to `LocalTraceSink`
- user can open the local viewer to inspect runs

Initial `aisuite-code` capabilities:

- create an agent with FileTools and ShellTools
- accept user prompts in a loop
- keep conversation state with `Runner.continue_sync(...)`
- ask before running high-risk tools such as shell or write-file
- write traces to `.aisuite/events.jsonl`
- print the viewer command or optionally start the viewer

Example session shape:

```text
aisuite-code

You: read the tests and run the focused suite

Assistant: I will inspect the tests first.

Tool request: list_files
Allowed automatically.

Tool request: read_file tests/toolkits/test_shell.py
Allowed automatically.

Tool request: run_shell "python3 -m poetry run pytest tests/toolkits -q"
Approve? [y/N] y

Assistant: The focused toolkit suite passed.

You:
```

### CLI Implementation Choice

The first implementation is Python at `cli/py/aisuite-code-cli` because it can
use the Python framework directly. The executable is `aisuite-code`. A future
TypeScript implementation can live under `cli/ts` with a richer terminal UI.

Recommended sequence:

1. Build a minimal Python CLI in `examples/cli`.
2. Use it to harden agent state continuation, approvals, tool traces, and viewer
   UX.
3. Once behavior is clear, consider a TypeScript CLI for a richer developer
   product experience.

## Before Postgres

Before adding Postgres persistence, we should have:

- FileTools and ShellTools exercised by the CLI.
- Subagent traces visible in the viewer.
- Tool approvals visible in the viewer.
- A stable JSONL event shape.
- Enough real traces to validate the future schema.

Then Postgres can implement the same `TraceStore` contract with tables/indexes
for runs, events, groups, metadata, tags, status, and timestamps.

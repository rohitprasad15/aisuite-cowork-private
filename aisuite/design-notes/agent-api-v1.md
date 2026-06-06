# aisuite Agent API v1

## Goals

The v1 Agent API should make simple agentic workflows easy while preserving
aisuite's provider-agnostic model. It should feel familiar to users of OpenAI's
Agents SDK, borrow Claude Agent SDK's simplicity where useful, and stay small
enough for novice users.

The core API is in-memory. Persistence should be possible later by serializing
`RunState`, but v1 should not introduce a `Session` abstraction.

Observability should be built in at the data-model level. v1 should expose
enough trace/span data for debugging and future export to OpenTelemetry, without
requiring a tracing backend or an OpenTelemetry dependency for basic use.

## Non-goals

- Persistent sessions or built-in storage adapters.
- A first-class `AgentFactory` class.
- Caller-provided `run_id` for idempotency.
- Multi-agent handoffs in the initial implementation.
- Guardrails, tracing exporters, or human approval workflows in the initial
  implementation.

These can be added later without changing the basic `Agent + Runner + RunState`
shape.

## API Summary

```python
import aisuite as ai


def get_weather(city: str) -> str:
    """Get weather for a city."""
    return "sunny"


agent = ai.Agent(
    name="weather_assistant",
    model="openai:gpt-4o",
    instructions="Answer briefly.",
    tools=[get_weather],
    tags=["weather"],
    metadata={"team": "growth"},
)

result = ai.Runner.run_sync(
    agent,
    "What is the weather in San Francisco?",
    max_turns=3,
    run_name="weather_lookup",
    group_id=f"user:{user_id}:weather",
    tags=["prod"],
    metadata={"request_id": request_id, "user_id": user_id},
)

print(result.final_output)
```

Continue from a previous result:

```python
result = ai.Runner.continue_sync(result, "What about tomorrow?")
```

OpenAI-style state continuation:

```python
state = result.to_state()
state.add_user_message("What about tomorrow?")

result = ai.Runner.run_sync(agent, state)
```

Persist and resume on another server:

```python
save_to_db(task_id, result.to_state().to_dict())

state = ai.RunState.from_dict(load_from_db(task_id))
agent = build_agent(state.metadata["task_type"])

result = ai.Runner.run_sync(agent, state)
```

## Agent

`Agent` is a declarative definition of model behavior. It should not own
execution.

```python
class Agent:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        instructions: str | None = None,
        tools: list[Callable] | None = None,
        model_settings: dict | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ): ...
```

Fields:

- `name`: Stable agent definition name, used in logs/results/state.
- `model`: aisuite model string, for example `"openai:gpt-4o"`.
- `instructions`: Optional system prompt inserted before user input unless the
  input already supplies a system message.
- `tools`: Python callables or supported aisuite tool definitions.
- `model_settings`: Default provider parameters such as `temperature` or
  `max_tokens`.
- `tags`: Agent-level observability tags.
- `metadata`: Agent-level structured metadata.

There is no `instance_name` and no `with_config()` in v1. Specialized agents can
be built by constructing another `Agent`.

## Runner

`Runner` owns execution.

```python
class Runner:
    @staticmethod
    async def run(
        agent: Agent,
        input: str | list[dict] | RunState,
        *,
        client: Client | None = None,
        max_turns: int = 5,
        run_name: str | None = None,
        group_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        tool_policy: ToolPolicy | Callable | None = None,
        tracing_disabled: bool = False,
    ) -> RunResult: ...

    @staticmethod
    def run_sync(...) -> RunResult: ...

    @staticmethod
    async def continue_run(
        result: RunResult,
        input: str | list[dict],
        **overrides,
    ) -> RunResult: ...

    @staticmethod
    def continue_sync(...) -> RunResult: ...
```

`input` semantics:

- `str`: converted to one user message.
- `list[dict]`: treated as the full starting message list.
- `RunState`: treated as an existing conversation/run state.

Runtime metadata:

- `run_name`, `tags`, and `metadata` are for observability and correlation.
- `group_id` links multiple traces for the same logical task or conversation.
  For example, a user task id, chat thread id, or app conversation id.
- Request ids, user ids, tenant ids, and task ids should be passed via
  `metadata`.
- v1 does not accept `run_id`. The runner may generate an internal run id for
  debugging/result identity.
- If explicit idempotency is needed later, add a clearly named
  `idempotency_key` parameter.

Tool security policy:

- `tool_policy` is an optional runtime hook that can allow or deny tool
  execution.
- Policy should be orthogonal to observability. The policy decides; tracing
  records the decision and outcome.
- v1 may define the public shape before deeply integrating it with every tool
  path.

## Supplemental: Tool Metadata And Invocation Policy

The tool policy system should keep the novice path frictionless while giving
power users a per-invocation hook for CLI approvals, RBAC, enterprise guardrails,
and audit logging.

Plain Python functions remain valid tools:

```python
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

agent = ai.Agent(
    name="assistant",
    model="openai:gpt-4o",
    tools=[get_weather],
)
```

No metadata or policy is required. If a user explicitly passes a Python
callable, the default behavior is to allow it.

Tools may optionally carry descriptive metadata:

```python
weather = ai.tool(
    get_weather,
    metadata=ai.ToolMetadata(
        category="external_api",
        risk_level="low",
        capabilities=["read_weather"],
    ),
)
```

Metadata does not enforce behavior by itself. It exists for:

- policy callbacks
- trace events
- local/SaaS observability UI
- audit logs
- future built-in toolkits such as file and shell operations

Built-in toolkits should attach metadata automatically. For example:

- `read_file`: category `filesystem`, risk `low`
- `write_file`: category `filesystem`, risk `medium`
- `run_shell`: category `shell`, risk `high`

High-risk tools should have local guardrails in the tool implementation itself.
For example, a shell toolkit should require `allowed_commands=[...]` unless the
user explicitly opts into `allow_all=True`. This keeps simple usage safe without
forcing every novice user to learn custom policies.

Every tool invocation may call a policy hook before execution:

```python
def policy(context: ai.ToolPolicyContext) -> ai.ToolPolicyDecision:
    if context.tool_name == "run_shell":
        approved = ask_user(
            f"Allow shell command: {context.arguments['command']}?"
        )
        return ai.ToolPolicyDecision(
            allowed=approved,
            reason="approved by user" if approved else "denied by user",
        )
    return ai.ToolPolicyDecision(allowed=True)

result = ai.Runner.run_sync(
    agent,
    "Run the tests",
    tool_policy=policy,
)
```

The policy context should include:

```python
@dataclass
class ToolPolicyContext:
    agent_name: str
    tool_name: str
    arguments: dict[str, Any]
    tool_metadata: ToolMetadata | None
    run_name: str | None
    trace_id: str | None
    parent_run_id: str | None
    group_id: str | None
    tags: list[str]
    metadata: dict[str, Any]
    messages: list[dict[str, Any]]
```

Convenience policies can cover common cases:

```python
ai.AllowAllToolPolicy()
ai.DenyAllToolPolicy(reason="maintenance window")
ai.AllowToolsPolicy(["read_file", "list_files"])
ai.RequireApprovalPolicy(callback=ask_user)
```

`RequireApprovalPolicy` should call the callback for each proposed invocation.
The callback may return `bool` or `ToolPolicyDecision`. This supports CLIs that
ask the user for permission interactively while preserving a simple synchronous
runner path.

The local viewer should display policy outcomes with the tool call:

- tool name
- category
- risk level
- allowed/denied
- reason
- decision metadata

This gives power users strong control without making the default API feel heavy.

`continue_sync(result, input)`:

- Reuses the agent, messages, metadata, tags, model settings, and client context
  from `result`.
- Appends the new input as user messages.
- Runs the agent again from the continued state.
- Should raise a clear error if the result cannot be continued.

## RunResult

`RunResult` is the public result object returned by `Runner`.

```python
class RunResult:
    final_output: str | object | None
    status: Literal["completed", "requires_input", "max_turns_exceeded", "failed"]
    agent: Agent
    last_agent: Agent
    input: str | list[dict] | RunState
    messages: list
    new_items: list
    raw_responses: list
    run_name: str | None
    trace_id: str
    group_id: str | None
    tags: list[str]
    metadata: dict
    steps: list[RunStep]

    def to_state(self) -> RunState: ...
```

Notes:

- `final_output`, `last_agent`, `new_items`, and `raw_responses` mirror OpenAI
  terminology where it fits.
- `messages`, `status`, `tags`, and `metadata` are aisuite-friendly additions.
- `final_output` should normally be `response.choices[0].message.content` for
  chat completion responses.
- `trace_id` is generated by aisuite for every runner invocation.
- `group_id` is copied from the run input or prior state to link related runs.
- `steps` is the provider-agnostic execution timeline.

## RunState

`RunState` is the serializable continuation object.

```python
class RunState:
    agent_name: str
    messages: list
    status: str
    run_name: str | None
    trace_id: str | None
    group_id: str | None
    tags: list[str]
    metadata: dict
    steps: list[dict]
    max_turns: int

    def add_user_message(self, input: str | list[dict]) -> None: ...
    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "RunState": ...
```

Serialization boundary:

- `RunState` stores conversation state and observability metadata.
- It must not serialize Python callables, provider clients, or tool
  implementations.
- On resume, application code rebuilds the relevant `Agent` definition and
  passes it with the loaded state.

## Observability And Tracing

The v1 observability design should be compatible with OpenAI's tracing concepts
without requiring OpenAI's backend. OpenAI's Agents SDK models tracing as:

- A trace for one end-to-end workflow.
- Spans for operations inside that workflow, such as agent execution, model
  generations, tool calls, handoffs, and guardrails.
- A `group_id` for linking multiple traces from the same conversation or task.
- Trace processors/exporters for sending data to OpenAI or another backend.

aisuite should use the same mental model with a lighter v1 implementation.

### RunStep

`RunStep` is the serializable span-like record exposed on `RunResult.steps` and
`RunState.steps`.

```python
class RunStep:
    id: str
    type: Literal[
        "agent",
        "model_response",
        "tool_call",
        "tool_result",
        "handoff",
        "custom",
    ]
    name: str | None
    trace_id: str
    parent_id: str | None
    started_at: str
    ended_at: str | None
    data: dict
```

Initial v1 can populate:

- One `agent` step per `Runner.run_sync(...)`.
- One `model_response` step for each provider call that can be observed.
- One `tool_call` and one `tool_result` step per executed tool where the
  existing tool runner exposes enough information.

If the existing client tool runner does not expose all intermediate events yet,
v1 may start with best-effort `agent` and `model_response` steps and expand
tool step fidelity as the runner is refactored.

### Trace Identity

Every `Runner.run*` invocation generates a `trace_id` unless tracing is
disabled. The generated id should be stable for the returned result/state.

`continue_sync(result, input)` should:

- Generate a new `trace_id` for the new runner invocation.
- Preserve `group_id`, tags, metadata, and prior messages from the previous
  result.
- Include prior steps in state for debugging, and mark new steps with the new
  trace id.

This mirrors the operational reality that each server invocation is separately
traceable, while `group_id` links the larger user task across continuations and
server boundaries.

### Tracing Configuration

Keep v1 simple:

```python
result = ai.Runner.run_sync(
    agent,
    "hello",
    run_name="support_reply",
    group_id=conversation_id,
    metadata={"request_id": request_id, "user_id": user_id},
    tracing_disabled=False,
)
```

Do not add a large `RunConfig` object in v1 unless the parameter list becomes
unwieldy.

### OpenTelemetry

Do not make OpenTelemetry a hard dependency in v1. Instead, design for an
optional bridge:

```python
ai.tracing.add_processor(ai.tracing.OpenTelemetryProcessor(...))
```

or:

```python
from aisuite.tracing.opentelemetry import OpenTelemetryProcessor

ai.tracing.add_processor(OpenTelemetryProcessor(tracer_provider=provider))
```

The internal tracing interface should be small:

```python
class TraceProcessor:
    def on_trace_start(self, trace: Trace) -> None: ...
    def on_trace_end(self, trace: Trace) -> None: ...
    def on_step_start(self, step: RunStep) -> None: ...
    def on_step_end(self, step: RunStep) -> None: ...
```

The OpenTelemetry processor can translate:

- `trace_id` / `group_id` to span attributes.
- `run_name` to root span name.
- `RunStep.type` to span attributes such as `aisuite.step.type`.
- `metadata` and `tags` to span attributes, with safe normalization.
- Model/tool information to semantic attributes where there is a clear match.

This lets Jaeger, Tempo, Honeycomb, Datadog, Arize, Langfuse, or any other
OpenTelemetry-compatible tool display aisuite agent runs later, while the v1
runtime remains dependency-light.

### Sensitive Data

Tracing may capture prompts, completions, and tool inputs/outputs. v1 should
prepare for a future `trace_include_sensitive_data` option, but the first
implementation can keep step data conservative:

- Include model names, agent names, tool names, timing, ids, and status by
  default.
- Avoid storing full prompt/completion/tool payloads in `RunStep.data` unless we
  explicitly add a sensitive-data flag.
- Keep full conversation content in `RunResult.messages` and `RunState.messages`
  because continuation requires it.

### Runs UI

The first UI should be a local/developer runs viewer, not a hosted tracing
service. It should consume serialized `RunResult.trace_to_dict()` and
`RunState.to_dict()` payloads.

Recommended first viewport:

- Runs table: run name, agent, status, model, started time, duration, tags,
  group id, request/user metadata.
- Run detail: message timeline, step timeline, final output, raw trace JSON.
- Tool panel: tool calls/results, allow/deny decisions, policy reasons.
- Continuation panel: current `RunState` JSON and a small input box to continue
  a run from persisted state.

Recommended data path:

```python
trace = result.trace_to_dict()
state = result.to_state().to_dict()
```

Then either:

- Write JSONL files locally for a simple static viewer.
- Send JSON payloads to an app-owned backend.
- Later export spans through OpenTelemetry.

Do not make the UI the persistence layer. It should read persisted run/trace
records from whatever store the application chooses.

For v1, a static/local viewer is enough:

```shell
python -m aisuite.agents.viewer traces.jsonl
```

This can be added after the core API settles. The API work required now is only
to keep `trace_to_dict()` and `RunState.to_dict()` stable and UI-friendly.

## Tool Security Policy

Tool execution needs a policy hook so applications can enforce local security
rules. Common uses:

- Allow or deny specific tools by name.
- Prevent high-risk tools from running in production.
- Validate arguments before execution.
- Require a human approval workflow later.
- Attach app-level authorization checks to tool calls.

The policy hook should run after the model requests a tool call and before the
tool function executes.

Recommended v1 interface:

```python
class ToolPolicyDecision:
    allowed: bool
    reason: str | None = None
    metadata: dict | None = None


class ToolPolicyContext:
    agent_name: str
    tool_name: str
    arguments: dict
    run_name: str | None
    trace_id: str | None
    group_id: str | None
    tags: list[str]
    metadata: dict
    messages: list


class ToolPolicy:
    def evaluate(self, context: ToolPolicyContext) -> ToolPolicyDecision: ...
```

Convenience callable form:

```python
def policy(context: ToolPolicyContext) -> bool | ToolPolicyDecision:
    return context.tool_name in {"get_weather", "search"}
```

Usage:

```python
result = ai.Runner.run_sync(
    agent,
    "Plan my trip",
    tool_policy=policy,
)
```

If the policy denies a tool call:

- The tool must not execute.
- `RunStep(type="tool_call")` should record the denied decision without storing
  sensitive arguments unless sensitive tracing is enabled.
- v1 can return a tool-result message describing the denial to the model, for
  example `{"error": "Tool call denied by policy", "reason": ...}`.
- If the denial should stop the run instead of returning an error to the model,
  add a future policy action such as `"deny_and_stop"`.

Suggested future decision shape:

```python
Literal["allow", "deny", "deny_and_stop", "require_approval"]
```

For v1, a boolean allow/deny decision is sufficient.

Implementation note: the existing client-level tool runner currently owns tool
execution. The Agent API can either:

- Extend `Tools.execute_tool(...)` to accept a policy callback.
- Or move the tool loop into `Runner` over time.

The least disruptive first implementation is to extend the existing tool
execution path with an optional policy callback and have `Runner` pass it
through.

## Relationship To Existing Client API

The initial implementation can delegate to:

```python
client.chat.completions.create(
    model=agent.model,
    messages=messages,
    tools=agent.tools,
    max_turns=max_turns,
    **agent.model_settings,
)
```

The existing `max_turns` tool runner should remain the canonical execution loop
for Python tools and MCP tools. `Runner` should adapt the result into a
`RunResult`.

## Error Handling

Recommended v1 errors:

- Missing or invalid agent model: surface the existing client `ValueError`.
- Invalid continuation input: raise `ValueError`.
- Attempting to continue a non-continuable result: raise `ValueError`.
- Serialization containing unsupported objects: raise `TypeError`.

## Future Extensions

These should fit without breaking the v1 shape:

- `Runner.run_streamed(...)`.
- `output_type` for structured outputs.
- Handoffs and `Agent.as_tool(...)`.
- Guardrails.
- Tool permission policies.
- Human approval workflows for tool calls.
- Persistent state stores.
- Tracing/export hooks.
- Explicit `idempotency_key`.

## Testing Strategy

The Agent API should be developed with provider-free unit tests first. Tests
should mock `Client.chat.completions.create` or `ProviderFactory.create_provider`
so they do not require API keys or optional provider SDKs.

### Unit Tests

`tests/agents/test_agent.py`

- `Agent` stores `name`, `model`, `instructions`, tools, model settings, tags,
  and metadata.
- Defaults are immutable per instance: missing `tools`, `tags`, and `metadata`
  become independent empty values.
- `Agent` accepts provider-qualified model strings but does not instantiate a
  provider during construction.

`tests/agents/test_runner.py`

- `Runner.run_sync(agent, "hello")` builds a user message and calls the client
  with `agent.model`.
- `instructions` are prepended as a system message for string input.
- Existing system messages are preserved and not duplicated.
- `model_settings` are passed through to the client.
- Runtime kwargs override agent model settings where supported.
- Agent tools trigger `tools=[...]` and `max_turns=...`.
- Runtime tool policy is passed to the execution layer.
- `RunResult.final_output` maps from
  `response.choices[0].message.content`.
- `RunResult.messages` includes the final/intermediate messages returned by the
  existing tool runner.
- Agent-level and run-level tags/metadata are merged predictably.
- `run_name` is preserved on `RunResult`.
- Existing client/provider exceptions are surfaced without wrapping unless there
  is a clear aisuite-specific error.

`tests/agents/test_continuation.py`

- `RunResult.to_state()` returns a serializable `RunState`.
- `RunState.to_dict()` and `RunState.from_dict()` round-trip.
- `RunState.add_user_message("next")` appends a user message.
- `Runner.run_sync(agent, state)` resumes from state messages.
- `Runner.continue_sync(result, "next")` is equivalent to
  `state = result.to_state(); state.add_user_message("next"); run_sync(agent, state)`.
- `continue_sync` preserves tags, metadata, run name, agent settings, and
  messages.
- Invalid continuation inputs raise `ValueError`.
- Attempting to serialize unsupported objects raises `TypeError`.

`tests/agents/test_tool_policy.py`

- Allowed tool calls execute normally.
- Denied tool calls do not execute the Python function.
- Denied tool calls are represented in run steps.
- Callable policies and `ToolPolicy.evaluate(...)` policies both work.
- Policy context includes agent name, tool name, arguments, tags, metadata,
  trace id, and group id.
- Policy decisions are serializable when included in steps/state.

### Integration Tests

Integration tests should be optional and marked, matching existing test
conventions:

```python
@pytest.mark.integration
@pytest.mark.llm
```

Suggested integration coverage:

- One real provider smoke test without tools.
- One real provider smoke test with a simple Python tool and `max_turns`.
- One MCP smoke test reusing the existing MCP fixtures.

These should not run in the default unit test suite.

### Coverage Goals

Initial coverage targets:

- `aisuite.agents`: 95%+.
- Runner/RunResult/RunState modules: 90%+.
- No reduction in existing `aisuite.client` or `aisuite.utils.tools` coverage.

The default fast suite should run with:

```shell
poetry run pytest tests/agents tests/client/test_client.py tests/framework tests/utils/test_tool_manager.py
```

### Compatibility Tests

Add tests for OpenAI-shaped usage:

```python
result = ai.Runner.run_sync(agent, "hello")
state = result.to_state()
result = ai.Runner.run_sync(agent, state)
```

Add tests for aisuite-native usage:

```python
result = ai.Runner.run_sync(agent, "hello")
result = ai.Runner.continue_sync(result, "follow up")
```

Both forms should produce the same message history and client calls.

# Agent Framework Usage

This guide shows the smallest useful path for building with the aisuite agent
framework. Use `Agent` to describe behavior, tools, and defaults. Use `Runner`
to execute the agent and get back a `RunResult`.

## Install and Configure

Install aisuite with the provider extras you need, then set the provider API key.
For OpenAI:

```bash
export OPENAI_API_KEY="..."
```

## Basic Agent

```python
import aisuite as ai


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is sunny."


agent = ai.Agent(
    name="weather_assistant",
    model="openai:gpt-4o",
    instructions="Answer briefly. Use tools when they help.",
    tools=[get_weather],
    model_settings={"temperature": 0.2},
    tags=["example", "weather"],
    metadata={"app": "weather_demo"},
)

result = ai.Runner.run_sync(
    agent,
    "What is the weather in San Francisco?",
    max_turns=3,
    run_name="weather_lookup",
    group_id="demo_conversation_1",
    metadata={"request_id": "req_1"},
)

print(result.final_output)
```

`Runner.run_sync(...)` accepts a string, a list of chat messages, or a
`RunState`. The runner builds the model request, runs tool calls when the agent
has tools, and returns a `RunResult`.

## Continue a Conversation

Use `Runner.continue_sync(...)` when you already have state to continue. The
state can come from an in-memory `RunResult` or from a persisted thread.

```python
next_result = ai.Runner.continue_sync(
    result,
    "What about Oakland?",
)
```

For persisted threads, pass the agent plus a `StateStore` and `thread_id`:

```python
store = ai.FileStateStore()

first = ai.Runner.run_sync(
    agent,
    "Start the task",
    state_store=store,
    thread_id="thread_123",
)

next_result = ai.Runner.continue_sync(
    agent,
    "Continue from the saved state",
    state_store=store,
    thread_id="thread_123",
)
```

Continuations keep the prior messages and run metadata. Each runner invocation
gets its own `trace_id`; use `group_id` to connect runs that belong to the same
task or conversation.

## Tool Policy

Pass `tool_policy` when you want to decide which tools can run.

```python
def allow_weather_tools(context: ai.ToolPolicyContext) -> bool:
    return context.tool_name == "get_weather"


result = ai.Runner.run_sync(
    agent,
    "What is the weather in San Francisco?",
    tool_policy=allow_weather_tools,
)
```

For reusable policies, aisuite also exports `AllowAllToolPolicy`,
`DenyAllToolPolicy`, `AllowToolsPolicy`, and `RequireApprovalPolicy`.

## Trace Output

Every run returns trace data on the result:

```python
result.print_trace()
result.write_trace_jsonl(".aisuite/runs.jsonl")
trace = result.trace_to_dict()
```

For event-style tracing, attach sinks when you run the agent:

```python
sink = ai.tracing.LocalTraceSink(".aisuite/events.jsonl")

result = ai.Runner.run_sync(
    agent,
    "What is the weather in San Francisco?",
    trace_sinks=[sink],
)
```

You can also configure default sinks once:

```python
ai.tracing.configure(ai.tracing.LocalTraceSink(".aisuite/events.jsonl"))
```

Use the local viewer to inspect saved runs:

```bash
python -m aisuite.agents.viewer --trace-file .aisuite/events.jsonl
```

## Result Fields to Use

- `final_output`: the final assistant output.
- `messages`: full conversation after the run.
- `new_items`: messages added by this run.
- `trace_id`: unique id for this runner invocation.
- `group_id`: optional id for grouping related runs.
- `steps`: span-like records for the agent, model responses, and tools.
- `to_state()`: serializable state that can be saved and resumed later.

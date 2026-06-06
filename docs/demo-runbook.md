# aisuite local-first demo runbook

This runbook is for demoing the current aisuite agent platform work. It pairs with `docs/demo-narrative.md`; framework builders should also read `guides/agent-harness-api.md`.

## Demo Goal

Show that aisuite provides:

- A simple **Agents API** for notebooks and application code.
- A local coding **agent harness** through `aisuite-code`.
- Local observability through the trace viewer.
- A clean future path to production with durable state, artifact stores, and managed trace sinks.

Core message:

> Build locally, observe locally, deploy later, optionally use managed observability.

## Setup

Run from the worktree root:

```bash
cd /Users/rohit/fleet/ro4d/aisuite-agent-framework
python3 -m poetry install
```

For real model calls:

```bash
export OPENAI_API_KEY=...
```

The notebook has a scripted no-key path, but the best demo uses a real key.

## Part 1: Notebook Agents API Demo

Start Jupyter:

```bash
python3 -m poetry run jupyter-notebook examples/agents/local_observability_demo.ipynb
```

Run these cells in order:

1. Imports.
2. Start an in-memory viewer.
3. Display the full viewer iframe.
4. Create the temporary real demo workspace.
5. Run the real OpenAI model + tools demo.
6. Display the focused viewer iframe.

What to say:

- The notebook shows the reusable Agents API directly.
- The core shape is simple: create `Agent`, call `Runner.run_sync`, pass trace sinks.
- The viewer is embedded inside the notebook, so local observability is part of the development loop.
- `?embed=1&trace_id=...` gives a focused run-only view for notebooks.

Point out in the viewer:

- Run metadata and trace id.
- Model send/response events.
- Tool calls and tool results.
- Final output.
- Token and latency metadata when available.

Fallback:

If `OPENAI_API_KEY` is unavailable, run the scripted trace demo cells. Be explicit that this proves viewer mechanics, not model quality.

## Part 2: CLI Agent Harness Demo

Create a clean workspace:

```bash
rm -rf /tmp/aisuite-cli-play
mkdir -p /tmp/aisuite-cli-play
```

Start the CLI with the local viewer:

```bash
./scripts/aisuite-code --cwd /tmp/aisuite-cli-play --viewer
```

What to say:

- `aisuite-code` is a local coding agent harness built on top of the Agents API.
- The harness adds the terminal loop, tools, approval policy, artifacts, traces, and reviewer subagent.
- It is a reference implementation for building richer domain-specific harnesses.

Suggested prompts:

```text
List files in this directory and tell me what you see.
```

```text
Create app.py with an add(a, b) function and a small main block, then run it.
```

```text
Show git status and summarize what changed.
```

```text
Ask the reviewer subagent to review the current changes.
```

What to point out in the terminal:

- Compact session header: model, cwd, tools, traces, artifacts.
- `Working...` indicates the agent turn started.
- Tool activity is compact by default.
- Permission prompts show action, risk, and summarized arguments.
- After a turn, the CLI prints a trace id and focused viewer URL.
- `/last` shows details for the last turn when needed.

Useful CLI commands:

```text
/help
/examples
/status
/viewer
/viewer start
/last
/clear
/exit
```

## Part 3: Local Observability Story

Open the viewer URL printed by the CLI.

What to say:

- The same trace model works from notebooks, CLI, scripts, and applications.
- Locally, traces can go to JSONL or an in-memory TraceStore.
- The viewer is a local-first observability surface.
- Future managed observability can consume the same normalized run/event model.

Point out:

- Multiple runs in the left navigation.
- Focused single-run URL.
- Tool timeline.
- Subagent run correlation.
- Artifact previews and on-demand artifact loading.

## Part 4: Promotion To Production Story

Local shape:

```python
viewer = ai.tracing.start_viewer(None, port=0, trace_store=ai.tracing.InMemoryTraceStore())
result = ai.Runner.run_sync(agent, user_input, trace_sinks=[viewer.trace_sink])
```

Production shape later:

```python
result = ai.Runner.run_sync(
    agent,
    user_input,
    state_store=PostgresStateStore(...),
    artifact_store=BlobArtifactStore(...),
    trace_sinks=[ManagedTraceSink(...)],
)
```

What to say:

- The agent and runner programming model stays the same.
- Local-only pieces become production adapters.
- StateStore supports resumability.
- ArtifactStore handles large tool inputs/outputs.
- TraceSink/TraceStore supports local viewer now and managed observability later.

## Common Issues

### `Command not found: aisuite-code`

Use the repo shim:

```bash
./scripts/aisuite-code --cwd /tmp/aisuite-cli-play --viewer
```

### `No module named openai`

Install CLI package dependencies:

```bash
cd cli/py/aisuite-code-cli
python3 -m poetry install
cd ../../..
```

### Jupyter metapackage fails on pandas

Do not install the `jupyter` metapackage. The repo already has `notebook` in dev dependencies. Use:

```bash
python3 -m poetry run jupyter-notebook examples/agents/local_observability_demo.ipynb
```

### Viewer shows no runs

Make sure the agent run used a trace sink:

```python
trace_sinks=[viewer.trace_sink]
```

For CLI, start with:

```bash
./scripts/aisuite-code --cwd /tmp/aisuite-cli-play --viewer
```

## Close

The key takeaway is that aisuite lets developers start simple, stay local, inspect every agent step, and later promote the same mental model to production infrastructure.

# Notebook local observability demo

The notebook demo is at:

```text
examples/agents/local_observability_demo.ipynb
```

Run it from the repository worktree:

```bash
python3 -m poetry run jupyter-notebook examples/agents/local_observability_demo.ipynb
```

It starts the local viewer from Python and embeds it with `IPython.display.IFrame`:

```python
store = ai.tracing.InMemoryTraceStore()
viewer = ai.tracing.start_viewer(None, port=0, trace_store=store)
display(IFrame(viewer.url, width="100%", height=720))
```

For a focused run-only view, append query parameters:

```python
display(IFrame(
    f"{viewer.url}?embed=1&trace_id={result.trace_id}&theme=dark",
    width="100%",
    height=720,
))
```

`embed=1` hides the top bar and left run navigation. `trace_id=...` selects the run to show. `theme=dark` or `theme=light` can force a notebook-friendly theme. This is better for notebook cells where horizontal space is limited.

The notebook contains two flows:

- A real OpenAI model + tools demo that requires `OPENAI_API_KEY` and uses file tools against a temporary workspace.
- A scripted provider demo that does not call a model, useful for showing viewer mechanics without a key.

The scripted path is intentionally labeled as scripted. It is not a substitute for proving model quality; it is a deterministic way to show trace, tool, artifact, and viewer behavior.

## CLI to viewer workflow

For the coding CLI, start the local viewer when launching the CLI:

```bash
./scripts/aisuite-code --cwd /tmp/aisuite-cli-play --viewer
```

After each agent turn the CLI prints the trace id. If the viewer is running, it also prints a focused viewer URL:

```text
Trace: trace_...
  focused viewer: http://127.0.0.1:PORT?embed=1&trace_id=trace_...
```

Use the full viewer when comparing multiple runs, and the focused URL when embedding or sharing the details for one run.

## App/server workflow

Applications can use the same local observability path by passing the viewer sink into `Runner.run_sync` or `Runner.continue_sync`:

```python
viewer = ai.tracing.start_viewer(None, port=0, trace_store=ai.tracing.InMemoryTraceStore())
result = ai.Runner.run_sync(agent, "Inspect the workspace", trace_sinks=[viewer.trace_sink])
```

For a file-backed local run, use `LocalTraceSink` plus the viewer:

```python
trace_file = Path(".aisuite/events.jsonl")
result = ai.Runner.run_sync(agent, "Do the work", trace_sinks=[ai.tracing.LocalTraceSink(trace_file)])
viewer = ai.tracing.start_viewer(trace_file, port=0)
```

## Agent API quickstart

For a minimal Agent API walkthrough without observability-specific wiring, use:

```text
examples/agents/agent_api_quickstart.ipynb
```

That notebook focuses on the smallest useful surface: `Agent`, `Runner.run_sync`, plain Python function tools, and `Runner.continue_sync`.

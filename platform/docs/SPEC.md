# Coding Agent Harness — v1 Spec (draft)

> Working codename: **`harness`** (package/name TBD). Status: draft for discussion.
> Reference (read-only, do not modify): `../aisuite-agent-framework` and its `aisuite-code` CLI.

## 1. Summary

An **open-source, provider-agnostic, interactive-terminal coding agent** — a Claude
Code / Codex-class tool — optimized as a **human-in-the-loop pair programmer**.

It is built on **our own agent loop**. `aisuite` (Python) is used **only as the
model-access layer**: provider-agnostic chat completions and tool-schema
normalization. We do **not** use aisuite's `Runner` / `max_turns` loop — we own the
turn loop, permissions, context management, and UX.

### Goals
- Run the same harness well across providers (OpenAI, Anthropic, Google, open models).
- Safe-by-default pair programming: the human approves consequential actions.
- Clean, observable, hackable core — instrumentation and extension are first-class.
- A credible open-source alternative to closed coding agents.

### Non-goals (v1)
- Token streaming (deferred — see §4).
- Workspace checkpoint / undo of file edits (deferred — see §10).
- Hooks / event automation (deferred — AGENTS.md + slash commands only, §11–12).
- A TypeScript implementation (later, once `aisuite-js` matures).
- Multi-agent orchestration beyond a single optional subagent tool.

## 2. Locked decisions

| Area | Decision |
|---|---|
| Runtime | Python; reuse aisuite-Python as the LLM layer |
| Loop ownership | Our own turn engine (not aisuite `Runner`) |
| Streaming | Out for v1; event-bus architecture retained for later |
| Edit primitive | Reuse aisuite file toolkit: `write_file`, `replace_in_file`, `apply_patch`, `apply_unified_diff` |
| Shell | Persistent shell session (cwd/env persist across calls) |
| Checkpointing | None in v1 |
| Customization | `AGENTS.md` ingestion + slash commands |
| Autonomy | Human-in-the-loop pair programmer (Plan / Normal / Auto modes) |

## 3. Architecture

```
┌─ TUI layer (Rich/Textual) ──────────────────────────────┐
│ renders the event stream · input box · approval prompts  │
│ inline tool calls · diff rendering · slash-command menu  │
├─ Harness core ──────────────────────────────────────────┤
│ Session · TurnEngine (loop) · ToolRegistry               │
│ PermissionEngine · ContextManager · ProjectContext       │
│ SlashCommands · EventBus · Tracing adapter               │
├─ Model access layer ────────────────────────────────────┤
│ ModelClient: provider-agnostic single-shot completions   │
│ via aisuite + tool-schema generation + capability probe  │
└─ aisuite (providers, auth, schema normalization) ────────┘
```

**Seam rule:** the core never imports a provider SDK. It asks `ModelClient` for
"one completion given messages + tools" and gets a normalized result. This
preserves provider-agnosticism and isolates the future streaming work to one place.

## 4. Model access layer

`ModelClient` wraps `aisuite.Client`:

- One method, conceptually:
  `complete(messages, tools, model, **settings) -> AssistantTurn`
  where `AssistantTurn` = assistant text + structured `tool_calls`.
- Implemented by calling aisuite **without `max_turns`** (manual tool-handling mode):
  the response carries `tool_calls` for us to execute in our own loop.
- **Tool schemas:** reuse aisuite's callable→JSON-schema generation
  (`aisuite.utils.tools`) so we don't reimplement docstring/type-hint schema
  extraction, but we keep our own `ToolRegistry` (richer per-tool metadata: risk,
  permission rule, renderer). The registry hands the access layer the JSON specs.
- **No streaming in v1:** `complete()` blocks and returns the full turn. The event
  bus emits a single `assistant_message` rather than `assistant_delta`s. When
  streaming lands later, only `ModelClient` and the event granularity change.
- **Async core over sync aisuite:** `complete()` is synchronous, but the engine runs
  it via `asyncio.to_thread(...)` so the event loop stays responsive (TUI renders,
  ESC/steering accepted) while the model call blocks in a worker thread. No async
  aisuite required. Caveat: a thread-wrapped blocking HTTP call can't be preempted
  mid-flight — on interrupt we **abandon** the in-flight result at the next boundary,
  not truly cancel it. True mid-call interruption arrives with streaming.
- **Capability probe:** record per-provider facts we already need (parallel tool
  calls? prompt caching? reasoning/thinking?) so behavior degrades gracefully.
- **Model switching:** model is per-session config, changeable via `/model`.

## 5. Turn engine (the loop)

Async core (so the TUI, interruption, and future streaming compose cleanly), but
with no token streaming the iterations are coarse-grained.

**One user turn = many model↔tool iterations** until the model returns no tool calls,
hits a rail, or is interrupted.

```
loop per user turn:
  1. ContextManager assembles request messages (system + AGENTS.md + history + budget)
  2. ModelClient.complete(messages, tools)         → assistant_message event
  3. if no tool_calls: emit turn_end, return
  4. for each tool_call:
       PermissionEngine.evaluate(call)             → permission_required (if ask)
       if denied: append tool-error result, continue
       ToolRegistry.execute(call)                  → tool_started / tool_finished
  5. append tool results to history; emit iteration_end
  6. check cancel + queued steering messages; loop
```

### Event model (the core contract)
`turn_start · assistant_message · tool_proposed · permission_required ·
tool_started · tool_finished · iteration_end · turn_end · error · interrupted`

(Streaming later adds `assistant_delta` / `tool_output_delta` without changing the rest.)

### Interruption & steering
- **ESC / interrupt:** a cancel token checked between iterations and between tool
  executions (mid-stream interruption arrives with streaming later). Stops cleanly,
  returns control, preserves partial state.
- **Steering:** messages typed while the agent works are queued and injected as the
  next user turn; an explicit "interrupt now" path can cut the current turn short.

### Safety rails (surfaced, never silent)
- Max iterations per turn (configurable) → stop + tell the user.
- Token-budget guard → trigger compaction (§9) or stop with a clear message.

## 6. Tool surface (v1)

Built by composing the existing aisuite toolkits (read-only reference, imported as a
dependency) plus two new components (persistent shell, todo).

| Tool | Source | Risk | Default policy |
|---|---|---|---|
| `read_file` / `read_file_lines` | aisuite `files` | low | auto |
| `list_files` / `glob` | aisuite `files` | low | auto |
| `search_files` (grep) | aisuite `files` (ripgrep upgrade later) | low | auto |
| `write_file` | aisuite `files` | medium | ask |
| `replace_in_file` | aisuite `files` | medium | ask |
| `apply_patch` (Codex envelope) | aisuite `files` | medium | ask |
| `apply_unified_diff` | aisuite `files` | medium | ask |
| `git_status` / `git_diff` | aisuite `git` | low | auto |
| `run_shell` | **new** persistent shell (§8) | high | ask |
| `todo_write` | **new** plan/task tracker | low | auto |

- **Edit primitive:** reuse the diff/patch family as decided. System prompt guides the
  model on when to use `replace_in_file` vs `apply_patch` vs `write_file` (the
  reference CLI's instructions are a good starting point).
- **`todo_write`:** maintains a structured task list rendered in the TUI — most of the
  "organized agent" feel for interactive work. Low risk, auto-approved.
- Other git operations (commit, branch) go through `run_shell` and are approval-gated.

## 7. Permission engine

The defining component for a pair programmer.

### Modes
- **Plan** — read-only. All writes/commands blocked; the agent proposes a plan.
- **Normal** (default) — auto on reads, **ask** on writes/commands.
- **Auto** — auto-approve everything (trusted repos / scripted runs).

Set at launch (`--mode`) and switchable live via `/mode`.

### Rules
Per-tool default, refined by argument patterns:
- edits: allow only if path resolves under the workspace root; ask otherwise.
- `run_shell`: match against a command-prefix allowlist; ask on miss.

### Memory scopes (precedence high→low)
1. **Session** — "always allow this command / this tool" for the rest of the session.
2. **Project config** — persisted allow/deny lists (§15).
3. **Built-in defaults** — the risk table above.

### Denial handling
A denied call returns a structured **tool error** to the model (`{"error": "...",
"reason": "..."}`) so it adapts; it never crashes the run. A future `deny_and_stop`
can halt the turn instead.

## 8. Persistent shell

A long-lived shell process per session (cwd + env persist across `run_shell` calls).

- Backed by a persistent subprocess (e.g. a managed `bash`/`sh` via pipes or
  `pexpect`); commands run in the live session so `cd`, `export`, activated venvs, etc.
  persist — a real shell, unlike the reference toolkit's per-call `subprocess.run`.
- **`Executor` boundary:** the shell runs behind a small `Executor` interface, with
  `LocalExecutor` in v1. This is the hedge that lets a `ContainerExecutor` /
  `VMExecutor` (§17) slot in later for sandboxing without touching the engine.
- Because it's a real shell, pipes/redirects/chaining are **allowed** (the reference
  toolkit blocks them); safety comes from the **permission engine**, not syntax bans.
- **Hardening:**
  - per-command timeout; kill runaway/hung commands.
  - enforce non-interactive execution; detect/guard prompts that would block forever.
  - capture stdout/stderr/exit code; large output offloaded to the artifact store
    with a preview (reuse aisuite's artifact mechanism).
  - command + cwd shown in the approval prompt.
- Open: sandboxing (container / restricted user) is out of v1 scope but the design
  shouldn't preclude it.

## 9. Context management

v1 keeps it lightweight but real (a common OSS-clone weak spot):
- **Token accounting** per request; show usage in the TUI and via `/context`.
- **File-read dedup:** avoid re-injecting unchanged file bodies; reference by handle.
- **Compaction:** `/compact` (manual) summarizes older turns, preserving recent turns
  + pinned items (task list, open files). **Auto-compaction** on budget pressure is a
  fast-follow once thresholds are tuned.
- **Cache-friendliness:** order the prompt so providers with prompt caching (Anthropic)
  benefit; no-op where unsupported.

## 10. Sessions & state

- Conversation persistence: serialize a `RunState`-like JSON (model, messages,
  mode, todos, permission session-memory) for **resume** (`/resume`, `--continue`).
- **No workspace checkpointing in v1** — file edits are reverted manually (via git).
  The design leaves room to add edit-snapshotting + `/undo` later without reshaping
  the session model.

## 11. Project context — `AGENTS.md`

- On session start, discover and load project conventions into system context:
  - workspace-root `AGENTS.md`, plus a global `~/.config/harness/AGENTS.md`.
  - **Open:** nested/subdir `AGENTS.md` discovery and precedence (propose: root +
    global in v1; nested as fast-follow).
- Content is injected into the system prompt under a clear, labeled section.
- `/init` scaffolds an `AGENTS.md` by inspecting the repo.

## 12. Slash commands

Two kinds:

- **Built-in:** `/help`, `/mode <plan|normal|auto>`, `/model <id>`, `/context`,
  `/compact`, `/clear`, `/resume`, `/init`, `/status`, `/exit`.
- **User-defined:** Markdown files discovered from `.harness/commands/*.md`
  (project) and `~/.config/harness/commands/*.md` (global). File format:
  ```markdown
  ---
  description: Run the focused test suite and summarize failures
  argument-hint: <path>
  ---
  Run the tests under {{args}} and summarize any failures with file:line refs.
  ```
  Invoking `/test src/foo` expands the body (with `{{args}}` substitution) into the
  next user prompt. Keep the format a small subset of the Claude Code command
  convention for familiarity.

## 13. Observability

- Reuse aisuite's tracing sinks (`LocalTraceSink` JSONL, in-memory) by adapting our
  event bus to `TraceEvent`s — we get the existing viewer for free.
- Every turn/tool/permission decision is a trace event (tool name, args summary,
  allow/deny + reason, timing, status).
- `--trace-file` and an optional local viewer launch, mirroring the reference CLI.

## 14. TUI / UX

- **Textual full TUI from the start** (not a Rich REPL MVP): conversation pane,
  input box, inline tool calls, approval modals, todo panel, status line. Async,
  which fits the async core (§4/§5) and future streaming.
- Approval prompt shows: action, risk, effect, argument preview, and choices
  `[y] once · [n] deny · [a] always this tool · [c] always this command`
  (the reference `ApprovalController` is a solid model).
- Inline rendering of tool calls and diffs; todo list panel; mode + model + token
  usage in a status line.

## 15. Configuration & layout

Per-project state under `.harness/` in the workspace; global under `~/.config/harness/`.

```
.harness/
  config.toml          # model, mode default, allow/deny lists, allowed_commands
  commands/*.md        # project slash commands
  events.jsonl         # traces
  artifacts/           # large tool outputs
AGENTS.md              # project conventions (workspace root)
```

`config.toml` (sketch):
```toml
model = "openai:gpt-5.5"   # default (key on hand); later: deepseek:...
mode  = "normal"
[permissions]
allow = ["read_file", "list_files", "search_files", "git_status", "git_diff"]
ask   = ["write_file", "replace_in_file", "apply_patch", "apply_unified_diff", "run_shell"]
allowed_commands = ["pytest", "python3", "git", "ls", "cat", "rg"]
```

## 16. Python package layout (proposed)

```
harness/                      # package (name TBD)
  __init__.py
  cli.py                      # entrypoint, arg parsing, session wiring
  session.py                  # Session: config, history, mode, permission memory
  engine.py                   # TurnEngine: the loop + event emission
  events.py                   # event types / EventBus
  model_client.py             # aisuite adapter (no-max_turns completions)
  tools/
    registry.py               # ToolRegistry: schema + metadata + execute
    files.py                  # wraps aisuite.toolkits.files
    git.py                    # wraps aisuite.toolkits.git
    shell.py                  # NEW persistent shell
    todo.py                   # NEW task tracker
  permissions.py              # PermissionEngine + modes + rules
  context.py                  # ContextManager: budgeting, dedup, compaction
  project.py                  # AGENTS.md discovery/loading
  commands.py                 # built-in + user slash commands
  tracing.py                  # event bus → aisuite TraceEvent adapter
  tui/                        # Rich/Textual rendering
```

## 17. v1 scope vs later

**v1:** own loop (blocking), Plan/Normal/Auto permissions, file+git+persistent-shell+
todo tools, diff/patch edits, AGENTS.md, slash commands, conversation resume,
lightweight context mgmt (manual `/compact`), tracing + viewer, Rich REPL UI.

**Fast-follow:** streaming + mid-stream interruption, auto-compaction, ripgrep search,
nested AGENTS.md, full Textual TUI.

**Later:** workspace checkpoint/undo, hooks, subagents/parallel orchestration,
sandboxing via `ContainerExecutor`/`VMExecutor` (rides with Auto/headless/CI mode),
the TypeScript implementation.

## 18. Open questions

1. ~~Async vs sync core~~ **RESOLVED:** async core, with sync aisuite calls wrapped in
   `asyncio.to_thread`. Responsive UI + boundary-level interruption without async
   aisuite. (See §4.) Shell subprocesses are killable; model HTTP calls are abandoned,
   not preempted, until streaming lands.
2. ~~TUI framework~~ **RESOLVED:** commit to **Textual** now (§14).
3. ~~Default model~~ **RESOLVED:** `openai:gpt-5.5` (key on hand); switch to DeepSeek later.
4. ~~AGENTS.md nesting~~ **RESOLVED:** root + global only in v1; nested as fast-follow.
5. ~~Shell safety ceiling~~ **RESOLVED:** v1 = permission-gating + per-command timeouts
   + non-interactive enforcement. Sandboxing (container/VM) is deferred to a later
   `ContainerExecutor`/`VMExecutor` behind the §8 `Executor` boundary — it rides with
   Auto/headless/CI mode, where the human-approval gate is removed.
6. ~~Reuse vs vendor the aisuite toolkits~~ **RESOLVED:** reuse via a path/editable
   dependency on `aisuite-agent-framework` (the toolkits are NOT in published
   `aisuite` 0.1.14 — they live only in that fork). Reuse `files` + `git`; replace
   `shell` with our persistent shell (§8); wrap reused tools in `ToolRegistry` for
   permission rules + renderers. Swap to published `aisuite` once toolkits ship there.
```

# Agent Platform — Phased Build Plan

Test-gated phases. **Each phase has an Outcome and Gate (test cases). No phase starts
until the prior gate passes. Definition of done per phase = gate tests green + reviewed.**
See [`PLATFORM-SPEC.md`](./PLATFORM-SPEC.md) for architecture and [`SPEC.md`](./SPEC.md)
for the `code` skill.

Codename `coworker`; Python package import name `coworker`. Provider = OpenAI SDK
(`chat.completions` only) until the P12 aisuite swap.

---

## Slice 0 — a runnable interactive coworker

### P0 — Provider layer
**Outcome:** `coworker` package skeleton; `ProviderClient` interface + `OpenAIProvider`
(OpenAI Python SDK, `chat.completions`); `AssistantTurn`/`ToolCall` dataclasses;
per-model capability probe. No agent loop yet.
**Gate:**
- package imports cleanly.
- `complete()` returns assistant text for a mocked OpenAI client (no network).
- a tool-call response is parsed into structured `ToolCall`s (name + parsed args).
- `capabilities(model)` returns expected flags for known models.

### P1 — Tools + permissions
**Outcome:** `ToolRegistry` wrapping aisuite `files`+`git` toolkits (schema gen + execute
+ per-tool metadata/renderer hooks); `PermissionEngine` with Plan/Interactive modes,
path/command-scoped rules, three memory scopes, denial→tool-error.
**Gate:**
- registry exposes correct JSON schemas for file/git tools.
- `read_file` returns content from a temp workspace; path traversal blocked.
- read auto-allowed; write/run requires approval; Plan mode blocks writes.
- denied call yields a structured tool-error (no execution).
- session allowlist ("always allow") persists within a session.

### P2 — Turn engine + event bus
**Outcome:** async owned loop running model↔tool iterations via `asyncio.to_thread` over
the provider; typed event stream; interruption between iterations; steering queue;
max-iteration safety rail.
**Gate (scripted/mock provider returning canned turns):**
- no-tool turn emits `assistant_message` → `turn_end`.
- tool turn: `permission_required` → approve → execute → result fed back → final answer;
  events in correct order.
- denied tool → tool-error appended, loop continues.
- max-iterations rail trips and is surfaced (not silent).
- interrupt between iterations stops cleanly, preserving partial state.
- steering message injects as the next turn.

### P3 — Persistent shell
**Outcome:** `LocalExecutor` persistent shell behind an `Executor` boundary; `run_shell`
tool; cwd/env persist; per-command timeout; non-interactive enforcement; output capture
with artifact offload for large output.
**Gate:**
- `cd` in one call changes cwd seen by the next call.
- env var exported in one call is visible in the next.
- a hanging/`sleep` command is killed at timeout.
- large stdout is offloaded to an artifact with a preview.
- exit code captured; non-zero handled.
- interrupt kills the running command.

### P4 — Memory + sessions
**Outcome:** `MemoryStore` adapter + `SQLiteMemoryStore`; `remember` tool; session
persistence (RunState-like) + resume; scopes global/workspace/session.
**Gate:**
- write/read memory round-trips in SQLite.
- workspace-scope isolation (A's memory not visible in B).
- session save → resume reconstructs history.
- `remember` tool persists and is retrievable.
- memory is listable + editable (curation path).

### P5 — Skills + the `code` skill
**Outcome:** `SkillRegistry` (skill = instructions+tools+metadata); built-in `code` skill
(files+git+shell+`todo` + coding prompt); user/project skill discovery; AGENTS.md
(root+global) loading; `todo` tool.
**Gate:**
- `code` skill registers and exposes the expected tools.
- activating a skill swaps available tools + system prompt.
- a project skill is discovered from its directory.
- AGENTS.md (root + global) is loaded into context.
- `todo` tool updates a structured task list.

### P6 — Control plane (server + events)
**Outcome:** FastAPI server: OpenAI-compatible `POST /v1/chat/completions` + WebSocket
event/approval stream + `/v1/sessions`, `/v1/skills`, `/v1/memory`, `/v1/permissions`.
**Gate:**
- `/v1/chat/completions` returns an OpenAI-shaped response (mocked provider).
- an OpenAI client library can call it (contract test).
- WS stream emits turn/tool/permission events for a session.
- approval over WS round-trips (`permission_required` → client decision → tool proceeds).
- session create/resume via the API.

### P7 — TUI surface (Textual)
**Outcome:** Textual client (conversation pane, input, inline tool calls, approval modal,
todo panel, status line: mode/model/tokens); entry points `coworker` and `coworker code`.
**Gate:**
- renders a turn from a scripted event stream (Textual pilot/snapshot test).
- approval modal accept/deny drives the decision.
- slash commands work (`/mode`, `/model`, `/context`, `/clear`, `/resume`).
- `--skill code` / `coworker code` boots directly into the code skill.

---

## Slice 1 — reach

### P8 — Task / outcome mode
**Outcome:** opt-in task mode: plan → execute → self-verify, with approval gates only on
consequential actions.
**Gate:** a task run produces a plan; executes with gated approvals; self-verifies;
consequential action still gated; Plan mode stays read-only.

### P9 — ACP server (IDE)
**Outcome:** ACP v1 agent server (`agentclientprotocol/agent-client-protocol`).
**Gate:** `initialize` negotiates `protocolVersion` 1; a prompt round-trips; tool
activity + file diffs surfaced via ACP; conformance against the reference ACP client.

### P10 — Desktop GUI
**Outcome:** React SPA client + Tauri shell + Python-runtime sidecar supervision;
Chat/Cowork/Code panes.
**Gate:** GUI renders a turn from the server event stream; approval UI works; Tauri
builds and launches the sidecar; Playwright happy-path passes.

---

## Slice 2 — breadth & hardening

### P11 — Messaging gateway
**Outcome:** `Connector` interface + one adapter (Telegram); strict permission policy for
untrusted input.
**Gate:** inbound message creates/continues a session; events render back to the channel;
strict policy enforced; prompt-injection guard holds on a hostile-input test.

### P12 — aisuite swap + sandbox + hardening
**Outcome:** `AISuiteProvider` behind `ProviderClient` (swap off the OpenAI SDK);
`ContainerExecutor`; remote-exposure auth hardening.
**Gate:** provider swap passes P0–P2 tests unchanged; container executor isolates
filesystem/network; auth gates remote access; loopback-only by default verified.

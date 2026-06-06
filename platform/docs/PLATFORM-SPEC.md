# Agent Platform — Spec (draft)

> Working codename: **agent-coworker** (name TBD). Branch: `platform/agent-coworker`,
> a worktree off `codex/agent-framework-tests` in `aisuite-private`. Develops in-repo so
> the platform and the aisuite agent framework (toolkits, tracing) co-evolve; consider
> extracting to its own repo once framework APIs stabilize. Push to `private`, never `origin`.
>
> Companion docs: [`SPEC.md`](./SPEC.md) — the interactive coding agent, now reframed as
> the platform's **coding surface/skill** (locked v1). [`GAPS.md`](./GAPS.md) — `aisuite-code`
> gap analysis.

## 1. Vision

A **provider-agnostic, open-source agentic coworker platform**: a headless agent runtime
exposed over an **OpenAI-compatible API + event protocol**, driven through multiple
surfaces (TUI, desktop GUI, IDE, messaging), with **persistent memory**, a **skills
system**, and first-class **integrations**. It is *more than a coding agent* — coding is
one skill among many — but human-in-the-loop oversight stays central.

Inspirations and what we take from each:
- **Claude Cowork** — outcome-oriented coworker, workspace-scoped, human retains
  consequential decisions; knowledge-work, not just coding; a real desktop surface.
- **OpenClaw** — self-hosted, integration-rich (files/calendar/messaging/browser),
  persistent memory, autonomy. (Also a cautionary tale: its published vulnerability
  taxonomy is why §12 security is elevated.)
- **Hermes Agent** — the integration spine: OpenAI-compatible everywhere, capability
  auto-detect, **ACP** for IDEs, an OpenAI-compatible **API server** as backbone,
  messaging gateways, memory + skills.

**Core thesis:** build the runtime + protocol once; surfaces and integrations are
plugins. This is what makes "more than a coding harness" tractable instead of three
half-built products.

## 2. Locked decisions

| Area | Decision |
|---|---|
| Shape | Headless runtime + OpenAI-compatible server + event stream; surfaces are thin clients |
| Provider (build) | OpenAI Python SDK first → migrate to **aisuite** later (both OpenAI-shaped) |
| Provider (expose) | Be an OpenAI-compatible server ourselves (the integration backbone) |
| Integrations v1 | OpenAI-compatible API server · MCP tools · IDE via ACP · messaging gateways |
| Surfaces | TUI (Textual) · Desktop GUI (web SPA + **Tauri** shell, Python sidecar) · IDE (ACP) · messaging |
| Autonomy | Interactive pair-programmer **primary** + opt-in **task/outcome** mode |
| Memory | Persistent cross-session memory is **core** |
| Skills | First-class **skills system**; the coding harness is the `code` skill |
| Runtime language | **Python** (reuses aisuite framework in the same tree) |
| GUI language | **TypeScript + React**, packaged with **Tauri** |
| Repo | In-repo branch off `codex/agent-framework-tests`; co-evolve; extract later |

## 3. Architecture

```
        ┌──────────────── Surfaces (clients) ─────────────────┐
   TUI (Textual)   Desktop GUI (React+Tauri)   IDE (ACP)   Messaging
        └───────────────────────┬─────────────────────────────┘
        Control plane:  OpenAI-compatible HTTP API  +  event/stream (WS/SSE)
        ┌───────────────────────┴─────────────────────────────┐
                       Agent Runtime (headless, Python)
   Session mgr · TurnEngine (loop) · ToolDispatch · PermissionEngine
   MemoryStore · SkillRegistry · Scheduler(later) · EventBus · Tracing
        └───────────────────────┬─────────────────────────────┘
   Integration framework:
     Providers (OpenAI SDK → aisuite, capability-probed)
     Tools (MCP) · Connectors (fs/workspace, messaging, browser-later)
     Memory backends (SQLite → Postgres) · Skills (built-in + user)
        └──────────────────────────────────────────────────────┘
```

**Seam rules:**
- Surfaces never embed agent logic — they render events and send commands over the
  control plane. A new surface = a new client, nothing in the core changes.
- The core never imports a provider SDK directly — only the provider integration does.
- The coding loop/permission/tool designs from `SPEC.md` are **reused** by the runtime;
  they don't fork.

## 4. Provider strategy

- **Build against the OpenAI Python SDK**, plain `chat.completions` semantics only.
  **Discipline:** do **not** depend on OpenAI-proprietary surfaces (Responses API,
  Assistants) — that keeps the aisuite migration a near drop-in client swap.
- **Capability probe per provider/model** (tool use, vision, parallel tool calls,
  streaming, prompt caching) → behavior degrades gracefully. (Hermes does this.)
- **Migration path:** a `ProviderClient` interface with `OpenAIProvider` (v1) and
  `AISuiteProvider` (later). aisuite is OpenAI-API-shaped, so the swap is contained.
- **We also expose** an OpenAI-compatible server (§9.1) — we are both a *consumer* and
  a *provider* of the format. Same request/response model on both edges.

## 5. Runtime core

- **Session** — the unit of work: `{ workspace, mode, history, memory scope, active
  skill(s), permission state }`. Sessions are addressable over the API and resumable.
- **TurnEngine** — the owned async loop (per `SPEC.md` §5): assemble request → provider
  completion (via `asyncio.to_thread` over the blocking SDK) → tool calls → permission →
  execute → loop. Emits the event stream. Interruption between iterations; steering
  queue. Reused verbatim from the coding-surface design.
- **ToolDispatch** — resolves tool calls to the active skill's tools + always-on tools +
  MCP tools; enforces the permission engine.
- **PermissionEngine** — modes (Plan/Interactive/Task), path/command-scoped rules, three
  memory scopes; approvals routed to whichever surface owns the session (§6). Same engine
  as `SPEC.md` §7, generalized to route approvals over the control plane.
- **MemoryStore** (§7), **SkillRegistry** (§8), **Scheduler** (later), **EventBus**,
  **Tracing** (reuse aisuite `tracing` sinks/viewer).

## 6. Control plane (server + events)

The runtime runs as a local server; every surface is a client.

- **OpenAI-compatible HTTP API:** `POST /v1/chat/completions` (so *any* OpenAI frontend
  works as a basic client) plus platform extensions under `/v1/sessions`, `/v1/skills`,
  `/v1/memory`, `/v1/permissions`.
- **Event stream:** WebSocket (or SSE) carrying typed events — superset of `SPEC.md`'s
  events plus `memory.updated`, `skill.activated`, `integration.event`,
  `permission_required` / `permission_resolved`.
- **Approval channel:** `permission_required` is emitted to the session's owning surface,
  which replies with a decision over the stream. This is what makes approvals work
  uniformly across TUI / GUI / IDE / chat.
- **Auth:** local-first (loopback + token). Remote exposure is opt-in and gated (§12).

## 7. Memory (persistent, cross-session)

- **Backend:** a `MemoryStore` adapter interface with `SQLiteMemoryStore` (default,
  zero-config, file under the workspace/global config) and `PostgresMemoryStore`
  (shared/hosted) — mirroring the framework's `StateStore`/`PostgresStateStore` pattern.
  Embeddings optional (fast-follow).
- **Scopes:** `global` (user-wide) · `workspace` (per project) · `session`.
- **Content:** durable facts, user preferences, task state, and rolling session
  summaries. Optional embeddings for relevance retrieval; recency as the baseline.
- **Write path:** explicit (the agent records a memory via a `remember` tool) +
  automatic (session summarization on compaction). **Human-visible and editable** —
  memory is inspectable/curatable, not a black box (a trust requirement).
- Distinct from conversation `RunState` (which is transient continuation state); memory
  is the long-lived layer above it.

## 8. Skills system

- A **skill** = a named, reusable capability: `{ instructions, tools, optional model
  settings, optional sub-runtime config, metadata }`. Aligns with the Anthropic
  "skills" concept and Hermes' skill model.
- **The coding harness is the `code` skill** — it bundles the `files`/`git`/persistent-
  shell/`todo` tools + the coding system prompt from `SPEC.md`. Nothing special-cased.
  There is **no separate coding binary**; the CLI/TUI can boot directly into this skill
  (`coworker code` / `--skill code`) for a focused "just code in the terminal" path.
- **Discovery:** built-in skills + user/project skill directories (a manifest +
  markdown instructions, mirroring the slash-command format in `SPEC.md` §12).
- **Activation:** routed by the surface (e.g. the GUI "Code" tab activates `code`), or
  selected by the agent for a task, or invoked explicitly.
- **Authoring / self-improvement** (Hermes-style) — agent-authored skills — is a
  later-stage feature, gated behind review.

## 9. Integrations (all four first-class)

### 9.1 OpenAI-compatible API server (backbone)
Expose the runtime at `/v1/chat/completions`. Any OpenAI-format frontend, tool, or our
own GUI can drive it. This is the substrate the other surfaces build on.

### 9.2 MCP tools
Consume MCP servers as the standard tool-plugin mechanism — aisuite already has MCP
client support (`aisuite.mcp`); the SkillRegistry/ToolDispatch surface MCP tools like any
other, under the same permission engine.

### 9.3 IDE via ACP
Run as an **Agent Client Protocol (ACP) server** — pinned to **protocol version 1**
(`protocolVersion` exchanged at `initialize`), per the `agentclientprotocol/agent-client-protocol`
spec — so ACP-capable editors (Zed, JetBrains, VS Code, MS Intelligent Terminal) connect
and render chat, tool activity, file diffs, and terminal inline. ACP is now a real
cross-vendor standard (25+ agents, an ACP registry), making it the standards-based path
to IDE integration. We implement the **agent side**; editors are the clients.

### 9.4 Messaging gateways
A `Connector` interface; adapters for Telegram / Discord / Slack map an inbound channel
to a session and stream events back as messages. One gateway process, many channels
(OpenClaw/Hermes pattern). **Highest untrusted-input surface → strictest permissions.**

> **Connector interface** generalizes 9.3/9.4 (and future fs/calendar/browser): an
> adapter that (a) maps an external event to a session input and (b) renders runtime
> events back to that medium.

## 10. Surfaces

- **TUI** (Python/Textual) — first surface; a client of the local server.
- **Desktop GUI** — **web SPA (TypeScript + React)** talking to the local server's API +
  event stream; packaged as a desktop app via **Tauri** (OS webview = small/secure; Rust
  sidecar supervises the Python runtime process). Cowork-style layout (Chat / Cowork /
  Code panes). Same UI runs in a browser. *(Electron is the fallback only if a pure-JS
  stack + max ecosystem is preferred over Tauri's footprint/security wins.)*
- **IDE** via ACP (§9.3). **Messaging** via gateways (§9.4).

## 11. Autonomy

- **Modes:** `Plan` (read-only) · `Interactive` (default; approval-gated) · `Task`
  (outcome mode) · `Auto` (later). Switchable per session.
- **Task/outcome mode:** goal → plan → execute with **approval gates only on
  consequential actions** → self-verify → deliverable. Builds on the existing permission
  modes; the human still owns consequential decisions (the Cowork stance).
- **Scheduled / background autonomy** (OpenClaw-style proactive runs) — **later**; it is
  the largest security surface and waits for the sandbox executor + hardened permissions.

## 12. Security model (elevated — first-class)

Autonomy × integrations × messaging × tools multiplies the attack surface; the published
OpenClaw vulnerability taxonomy is the warning. v1 commitments:

- **Workspace scoping** — a designated folder is the controlled environment (Cowork
  model); filesystem tools are root-scoped (the `files` toolkit already enforces this).
- **Permission engine everywhere** — approvals routed to the owning surface; consequential
  actions always gated outside `Auto`. Untrusted-input surfaces (messaging) default to the
  strictest policy and a tool allowlist.
- **Prompt-injection awareness** — content arriving via tools/messaging/web is untrusted;
  never auto-escalate privileges from tool output. Least privilege per skill/connector.
- **Secrets/auth** — integration credentials stored outside the model context; never
  echoed into prompts or traces.
- **Sandbox executor** — the `Executor` boundary from `SPEC.md` §8 (`LocalExecutor` now;
  `ContainerExecutor`/`VMExecutor` later) gates how much of autonomy/background mode we
  enable.
- **Local-first** — server binds loopback by default; remote/network exposure is explicit,
  authenticated, and documented.

## 13. Configuration & layout

```
~/.config/agent-coworker/         # global: providers, keys ref, default model/mode, global skills, global memory
<workspace>/.agent-coworker/      # per-workspace: config, session state, memory(SQLite), traces, artifacts, project skills/commands
AGENTS.md                         # per-workspace conventions (root + global; §11 of SPEC.md)
```

**In-repo code layout** (under top-level `platform/`, kept separable for future extraction):
```
platform/
  docs/         SPEC.md · PLATFORM-SPEC.md · GAPS.md
  runtime/      Python: session, engine, tools, permissions, memory, skills, server
  surfaces/
    tui/        Textual client
    gui/        TypeScript + React app + Tauri shell
  integrations/ openai_server/ · mcp/ · acp/ · messaging/
  skills/       code/ (the coding harness) · <others>
```
Depends on `aisuite` (same tree, this branch) for providers/toolkits/tracing/MCP.

## 14. Build staging (scope discipline)

All four integrations are first-class *architecturally*; build order is staged so we
ship a working spine before breadth. Adjust as desired.

- **Slice 0 — spine:** runtime + TurnEngine + permission engine + OpenAI-compatible
  server + event stream + **TUI** + memory (SQLite) + **`code` skill** + **MCP**.
  Provider: OpenAI SDK. *(This is a runnable agentic coworker.)*
- **Slice 1 — reach:** **ACP** IDE surface + **desktop GUI** (React+Tauri) + **Task mode**.
- **Slice 2 — breadth/hardening:** **messaging gateways** + skill authoring + scheduler +
  **aisuite** provider swap + sandbox `Executor` + remote-exposure hardening.

## 15. Open questions

1. ~~GUI shell~~ **RESOLVED:** Tauri.
2. ~~Server-layer language~~ **RESOLVED:** **Python (FastAPI)** for runtime + server —
   the heavy logic (loop, toolkits, MCP, tracing, providers) is mature Python here and
   the server is thin I/O-bound glue; OpenAI-compatible Python servers are well-trodden
   (LiteLLM, vLLM). Node only wins at hosted multi-tenant scale → revisit a Go/Node edge
   then. GUI(TS)↔server type-sharing via generated OpenAPI types, not a shared language.
3. ~~Memory store~~ **RESOLVED:** `MemoryStore` adapter with `SQLiteMemoryStore` (default)
   + `PostgresMemoryStore` (§7). Embeddings: fast-follow.
4. ~~ACP version~~ **RESOLVED:** pin **protocol version 1** against `agentclientprotocol/
   agent-client-protocol`; implement the agent side (§9.3).
5. **Naming** — product/codename. *(still open)*
6. ~~Coding-surface reconciliation~~ **RESOLVED:** one product — coding is the `code`
   skill, no separate binary; CLI/TUI boots directly into it (`--skill code`). See §8.
```

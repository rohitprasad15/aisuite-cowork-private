# Coworker Platform — Handoff Guide

For a future agent/developer picking this up. Read this first, then `PLATFORM-SPEC.md`
(vision/architecture), `PLAN.md` (phases), `GUI-DESIGN.md` / `GUI-BACKLOG.md` (UI).

## 0. TL;DR
A **provider-agnostic, open-source agentic coworker platform**. A headless Python runtime
(the agent loop + tools + permissions + memory + skills + MCP + connectors + automation)
exposed over an OpenAI-compatible + WebSocket server, with thin clients (a Textual TUI and a
React GUI). Built on `aisuite` as the LLM layer (NOT its blocking `Runner` — we own the loop).

**Four surfaces** (see `SURFACES.md`): three ephemeral session surfaces — **Chat** (no
workspace), **Code** (a repo), **Cowork** (deliverable-oriented, a workspace) — plus
**MyHelper**, the *one* always-on persistent helper (single continuous thread, reachable in
the app + over Telegram/Slack). Also live: **MCP** tools, **messaging connectors**, **web
search**, and **scheduled automations**.

- Branch: **`platform/agent-coworker`** (worktree at `/Users/rohit/fleet/ro4d/agent-platform`),
  forked off `codex/agent-framework-tests` in **`rohitprasad15/aisuite-private`**.
- Push to **`private`**, never `origin` (origin = public andrewyng/aisuite).
- Commits: attribute to **Rohit Prasad <rohit.prasad15@gmail.com>**, **no AI co-author**.

## 1. Run it
```bash
cd /Users/rohit/fleet/ro4d/agent-platform/platform
./.venv/bin/python -m pytest tests -q            # tests (141, all pass)

# real run — server + GUI (two terminals):
export OPENAI_API_KEY=sk-...                       # or: source aisuite-agent-framework/.env
./.venv/bin/coworker-server --port 8765            # global storage in ~/.config/coworker
cd surfaces/gui && npm run dev                      # http://localhost:1420

# TUI:
./.venv/bin/coworker --cwd <project>

# Desktop (macOS dev build, see docs/DESKTOP.md) — needs Rust + Tauri CLI (one-time):
#   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && source "$HOME/.cargo/env"
#   cd surfaces/gui && npm i -D @tauri-apps/cli@^2
cd surfaces/gui && npm run tauri dev               # native window; sidecar server on a free port
```
- **Model API key without a shell env:** a Finder-launched desktop app can't read your shell,
  so the key is resolved env `OPENAI_API_KEY` → else SecretStore (`provider:openai`), set via
  **Manage → Settings** (`GET/POST /v1/settings*`, status-only). `providers.resolve_api_key`.
- Dedicated venv at `platform/.venv` (Python 3.13). **aisuite is imported from this
  worktree via a `.pth`** in the venv (NOT PyPI — the toolkits/agents only exist on this
  branch). Base deps: `docstring_parser`, `pydantic`, `openai`, `textual`, `fastapi`,
  `uvicorn`, `httpx`, `mcp` (MCP client), `ddgs` (keyless web search), `croniter`
  (scheduler), `pytest`, `pytest-asyncio`. **Optional extra `[messaging]`** =
  `python-telegram-bot` + `slack-bolt` (only the inbound listeners need them; outbound is
  pure httpx) — installed in this venv.
- Default model `gpt-5.5` (confirmed valid). `--cwd` is an optional seed; the GUI Code/Cowork
  tabs require choosing a folder (mandatory gate), Chat needs none.
- The server hosts the **always-on subsystems** (MyHelper gateway, MCP pool, scheduler) in
  its FastAPI lifespan — so "always-on" = "while `coworker-server` runs".

## 2. Architecture (layers)
```
Surfaces (thin clients):  TUI (Textual)   ·   GUI (React/Vite)   ·   Desktop (Tauri shell, macOS dev)
        │  WebSocket events+approvals  +  OpenAI-compatible / REST
Server (FastAPI):  coworker/server/{app,manager,run}.py
        │
Runtime (Python):  TurnEngine (loop) · ToolRegistry · PermissionEngine ·
                   Memory · ConversationStore · Agents · Skills · Config ·
                   SecretStore · MCP pool · Connectors/Gateway · Web search · Automation
        │  ProviderClient (complete + stream)
aisuite:  providers (OpenAI now) · toolkits (files/git)   |   mcp SDK · ddgs · croniter
```
**Seam rule:** surfaces never embed agent logic — they render the event stream and send
commands. The engine owns the loop; the provider is the only thing that touches an LLM SDK.

## 3. Core concepts (and the files)

### Agents vs Skills — the key distinction
- **Agents** = Code / Chat / Cowork. Top-level surfaces; each has its **own system prompt
  + base toolset + `needs_workspace` flag**. `coworker/agents/` (`base.Agent`,
  `code.py`, `chat.py`, `registry.py`). Code needs a workspace (files/git/shell/todo);
  Chat doesn't (conversation + memory + load_skill).
- **Skills** = Anthropic **SKILL.md** capabilities, loadable by ANY agent. Prompt-level,
  **progressive disclosure**: only the catalog (name+description) is injected; a
  `load_skill(name)` tool pulls the full body on demand. `coworker/skills/base.py`
  (`SkillLoader`, `skill_tools`, `skill_catalog_text`). Discovered from
  `~/.config/coworker/skills/<name>/SKILL.md` (global) + `<ws>/.coworker/skills/`.
- These are **complementary**: skills are prompt-level; MCP/connectors (future) are
  tool-level (callable tools added to the model's tool list).

### Engine assembly
- `coworker/agent.py` → **`build_engine(agent=…, workspace=…, …)`** wires: the agent's base
  tools + AGENTS.md (workspace agents) + memory `remember` + injected memories + the skill
  catalog + `load_skill` → a `TurnEngine`. `build_code_engine(**kw)` is a **shim** =
  `build_engine(agent=code_agent(), **kw)` (kept for the TUI/older tests).

### The loop
- `coworker/engine.py` `TurnEngine`. Async. One user turn = many model↔tool iterations.
  Consumes `provider.stream()` via a thread+`asyncio.Queue` bridge → emits `assistant_delta`
  then the canonical `assistant_message`. Tools execute (permission-checked), results fed
  back. Emits a typed event stream (`coworker/events.py`): `turn_start, assistant_delta,
  assistant_message, tool_proposed, permission_required, tool_started, tool_finished,
  iteration_end, turn_end, error, interrupted`. Interruption is checked **between**
  iterations; steering messages queue and inject as the next turn; a max-iterations rail
  stops runaway turns (surfaced, not silent). Approvals are out-of-band via an injected
  async `approver`.

### Providers
- `coworker/providers/` — `ProviderClient` (abstract: `complete`, `capabilities`, and
  `stream` with a default that wraps `complete` as one chunk). `OpenAIProvider` implements
  real SSE streaming (accumulates tool-call args across chunks). **Plain `chat.completions`
  only** — no Responses/Assistants API, so the future aisuite swap stays a near drop-in.

### Tools & permissions
- `coworker/tools/registry.py` `ToolRegistry` — wraps callables (incl. aisuite `files`/`git`
  toolkits), reuses aisuite `Tools` for schema-gen, owns execution. Supports an explicit
  **schema override** (`schema=` arg or a `__coworker_schema__` attr) for tools whose
  signature can't auto-convert.
- `coworker/tools/shell.py` — **persistent** shell (`LocalExecutor` behind an `Executor`
  ABC — the seam for a future Container/VM sandbox). One long-lived bash; cd/env persist.
- `coworker/tools/todo.py` — `todo_write` + `TodoList`.
- `coworker/permissions.py` `PermissionEngine` — modes **Plan / Interactive / Auto /
  Custom**. Custom = interactive + auto-approve the config's `auto_allow` tools. Path
  scoping for writes; command-prefix allowlist; session allowlists; denial → tool-error
  (not a crash). Decisions return `needs_user` → the surface prompts.

### Memory, sessions, config
- `coworker/memory/` — `MemoryStore` adapter + `SQLiteMemoryStore`; scopes global/workspace/
  session; `remember` tool; injected into the system prompt.
- `coworker/conversations.py` `ConversationStore` — **the unified, global session store**:
  SQLite **index** (`~/.config/coworker/coworker.db`: sessions→project/title/agent/n_msgs,
  workspaces, memory) + **append-only `conversations/<id>.jsonl` per conversation**.
  Lazy-migrates legacy inline blobs. `coworker/sessions.py` = `SessionRecord`.
- `coworker/config.py` — layered TOML: defaults < `~/.config/coworker/config.toml` <
  `<ws>/.coworker/config.toml`. Keys: model, mode, max_iterations, allowed_commands,
  auto_allow, host, port.
- `coworker/project.py` — AGENTS.md loading (root + global).

### Server & GUI
- `coworker/server/manager.py` `SessionManager` — owns per-session engines (keyed by
  session_id), the stores, the provider; builds engines **per agent**; resolves/canonicalizes
  workspaces; lists agents/skills/sessions/recents.
- `coworker/server/app.py` — FastAPI. **WS** `/ws/session/{id}?workspace=&agent=` streams
  events + routes approvals (asyncio.Queue) + `set_mode`/`set_model`/`interrupt`. **REST**:
  `/v1/chat/completions` (OpenAI proxy), `/v1/agents`, `/v1/skills`, `/v1/sessions[/{id}/messages]`,
  `/v1/memory`, `/v1/workspaces/{recent,open}`, `/v1/health`.
- `coworker/tui/app.py` — Textual client. `surfaces/gui/` — React/Vite SPA (thin WS client):
  `App.tsx` (state + 3 surfaces: session / superagent / scheduled), `components/` (Sidebar,
  Transcript, Composer, FolderGate, ManageModal, SuperAgentView, ScheduledView), `api.ts`.

### The four surfaces & MyHelper
- `coworker/agents/` — `code`, `chat`, `cowork` (deliverable-oriented, workspace; shares its
  tool factory with myhelper), `myhelper` (own persistent-assistant prompt, renameable).
  `list_agents()` = the 3 *session* surfaces (Code/Chat/Cowork); MyHelper is the always-on
  one. Full model in `SURFACES.md`.
- **MyHelper = the super-agent.** One persistent engine in the manager (`SuperAgent`,
  `__superagent__` session), single continuous thread fed by a queue; idle → a `user` turn,
  busy → injected via `TurnEngine.queue_steering()`. Replies over chat go via the
  `send_message` tool; the GUI surface streams its events over `/ws/superagent` and can
  approve its risky tools (approver wired to connected GUI clients; deny when unwatched).

### Secrets, MCP, connectors, web, automation (the new subsystems)
- `coworker/secrets.py` `SecretStore` — one `0600` JSON store (`~/.config/coworker/secrets.json`),
  `${VAR}` refs resolved at read, status-only API. Holds connector tokens + web-search keys.
- `coworker/mcp/` — our **own async MCP client** on the `mcp` SDK (not aisuite's sync one).
  `mcp.json` (global+workspace), `MCPManager` (one task per server), tools bridged via
  `run_coroutine_threadsafe`, named `mcp__<server>__<tool>`. `/v1/mcp*`. See `MCP-CONNECTORS-SPEC.md`.
- `coworker/connectors/` — messaging. Outbound `send_message(target,text)` (every agent,
  stateless httpx senders). A `Gateway` + `BasePlatformAdapter`s (Telegram long-poll, Slack
  Socket Mode, lazy-imported `[messaging]`); allowlist guard; chat-ID auto-capture (recent
  senders). Guided connect wizard via `descriptors.py` + `/v1/connectors*`.
- `coworker/web/` — `web_search` tool for every agent. `WebSearchProvider`: keyless
  **DuckDuckGo** default + configurable Tavily/Brave (`web_search:default` secret /
  `web_search_provider` config). `/v1/web-search`.
- `coworker/automation/` — scheduled tasks. A task is its **own persistent entity** that runs
  **fresh each fire**; SQLite `TaskStore` + a `Scheduler` tick loop (run-once-catch-up,
  skip-on-overlap), `create/list/update/delete_scheduled_task` tools (Cowork+MyHelper;
  create gated = approve-at-creation; agent converts NL→cron), `/v1/automations*`, GUI
  **Scheduled** view. Schedules default to the **machine's local timezone**. See
  `AUTOMATION-SCHEDULING.md`.

## 4. Gotchas (hard-won — read these)
1. **Path canonicalization.** macOS `/tmp` → `/private/tmp` symlink bit us: the same folder
   got keyed two ways, splitting sessions. **Always `os.path.realpath` workspace paths**
   (store + query). `ConversationStore.canonicalize_workspaces()` migrates old rows.
2. **`todo_write` schema.** A bare `list` annotation generates a JSON schema OpenAI
   **rejects** (`"<class 'list'>" is not valid`). Hence the `__coworker_schema__` override
   on tools. Only caught by a *live* call — unit mocks won't.
3. **SQLite cross-thread.** The WS handler runs on a different thread than the store was
   created on → `check_same_thread=False` + an `RLock` on every op.
4. **Streaming bridge.** `provider.stream()` is a **blocking generator**; the engine runs it
   in `loop.run_in_executor` and pushes chunks via `loop.call_soon_threadsafe(queue.put_nowait,…)`.
   Interruption is **between iterations** — a thread-wrapped blocking HTTP call can't be
   preempted; we abandon its result at the next boundary. True mid-call interrupt needs
   streaming-level cancellation (not done).
5. **Persistent shell signals.** `killpg(SIGINT)` kills *bash itself* (non-interactive bash
   dies on SIGINT). Instead we `pgrep -P <shell_pid>` and SIGINT the **child**, so the shell
   survives; on timeout we keep reading until the command's marker line resyncs the stream;
   hard-kill only if SIGINT fails.
6. **The engine streams, always.** It calls `provider.stream()`, not `complete()`. Test
   doubles must subclass `ProviderClient` (to inherit the default `stream`) or implement
   `stream`. Don't feed a non-streaming fake OpenAI client to `OpenAIProvider` and expect
   the engine to work.
7. **Mode/model changes must go over the WS** (`set_mode`/`set_model`). The composer pill
   was once cosmetic — changing local state did nothing to the engine.
8. **aisuite via `.pth`.** Not pip-installed. If imports break, check the `aisuite_src.pth`
   in the venv site-packages points at the worktree root.
9. **Chat has no workspace.** `manager.get_engine` returns `None` only when an agent
   `needs_workspace` and there's no valid folder; Chat builds with `workspace=None`.
10. **MCP is async-native, not aisuite's `MCPClient`.** aisuite's connects on its own loop +
    `nest_asyncio` — fatal in our async server. We use the `mcp` SDK directly; each server
    runs in its **own task** (anyio cancel scopes are task-local — enter/exit must be one
    task); sync tool calls bridge back via `run_coroutine_threadsafe`.
11. **Unattended approvals.** MyHelper inbound + scheduled runs have no human at a screen. The
    super-agent approver prompts **connected GUI clients** (deny when none). Scheduled runs
    auto-allow deliverable writes within the task workspace + a per-task "always-allowed" set;
    deny new consequential actions. Don't run these in blind AUTO mode.
12. **Scheduler timezone.** Schedules default to the **machine's local zone** (`"local"`),
    not UTC — for a local-first tool "8:05 PM" means the user's clock. A UTC default once made
    a task fire 7h off. Explicit IANA tz still overrides.
13. **Tools registered conditionally in `build_engine`.** `send_message` only when a connector
    is configured; `web_search` always; scheduling tools only for Cowork/MyHelper with a
    workspace + a `task_store`. Tests assert presence/absence — keep the conditions in mind.

## 5. Testing
141 tests in `platform/tests/` (incl. `test_secrets`, `test_mcp`, `test_connectors`,
`test_web_search`, `test_automation`, `test_settings`). Patterns: `ScriptedProvider(ProviderClient)` returns
queued `AssistantTurn`s; FastAPI `TestClient` for REST/WS; injected fakes for providers,
adapters (`FakeAdapter`), web-search providers, and the scheduler's `runner` — **no network,
no LLM, no live MCP/bot**. Live smokes were run by hand (a real filesystem MCP server, a real
DuckDuckGo query, a real scheduled Cowork run) but aren't in the suite. GUI: `npm run build`
(tsc strict + vite) is the check; no JS test runner yet.

## 6. Status & roadmap
**Done (core):** Code + Chat + **Cowork** + **MyHelper** surfaces; owned async loop;
**streaming**; permissions (Plan/Ask/Full/Custom) + model picker (live via WS); persistent
shell; memory; unified append-only session store + project grouping + transcript replay;
SKILL.md skills (catalog + load_skill); layered config; folder picker / New project; React GUI.

**Done (subsystems):**
- **C0 SecretStore** (`coworker/secrets.py`) — `0600` JSON, `${VAR}` refs, status-only.
- **C1 MCP** (`coworker/mcp/`) — own async client on the `mcp` SDK; global+workspace
  `mcp.json`; permission-gated `mcp__<server>__<tool>`; `/v1/mcp*` + **GUI MCPs tab**.
- **C2 Messaging** (`coworker/connectors/`) — outbound `send_message` (all agents); gateway +
  Telegram/Slack adapters (`[messaging]` extra); **MyHelper super-agent** owns inbound (one
  thread, queue+steering); allowlist + **chat-ID auto-capture**; guided connect wizard
  (`/v1/connectors*` + Connectors tab); first-class **GUI MyHelper surface** (`/ws/superagent`,
  message + approve in-app).
- **The four surfaces** (`SURFACES.md`) — Cowork is its own session surface; MyHelper its own
  agent/prompt, renameable.
- **Web search** (`coworker/web/`) — keyless DuckDuckGo + configurable Tavily/Brave.
- **Automation/Scheduling** (`coworker/automation/`, `AUTOMATION-SCHEDULING.md`) — task store +
  scheduler + tools + `/v1/automations*` + GUI **Scheduled** view; verified live end-to-end.
- **Desktop (Tauri, macOS dev build)** (`surfaces/gui/src-tauri/`, `docs/DESKTOP.md`) — native
  window over the SPA; free-port **sidecar** server + endpoint injection (single codebase);
  **tray** (close-to-tray keeps MyHelper + scheduler alive); **overlay title bar** (traffic
  lights float, edge-to-edge); **autostart** (Open-at-login) + **keep-awake** (caffeinate)
  toggles; native folder picker; first-run **onboarding wizard** (workspace, model+key,
  always-on toggles) + a **Settings** tab (model key in SecretStore, default model, toggles,
  "Run setup again"). **Verified live** end-to-end via `npm run tauri dev` (window opens,
  sidecar managed + killed on exit, endpoints injected, prefs persist). 141 tests pass.

**Next / not built:**
- **Cowork capabilities:** **document generation** (Word/Excel/PPT/PDF — keyless,
  python-docx/openpyxl/python-pptx) ← likely next; **PDF read** (`read_pdf`, pypdf/pdfplumber).
- **Automation polish:** richer schedule *confirm card* (v1 uses the generic approval); live
  artifacts; desktop "keep awake".
- **MyHelper:** "ask in the channel" approval (approve risky actions over Telegram/Slack when
  away from the GUI); later — MyHelper spins off Cowork/Code sessions.
- **C3–C4 Connectors:** Google OAuth (Gmail+Calendar) → Browser (Playwright); managed one-click
  OAuth for the cloud build.
- **Platform:** desktop **Phase 4** PyInstaller `.dmg` (aisuite `.pth` wrinkle) — the dev build
  + onboarding/tray/autostart/keep-awake are done; **context compaction** (deferred); **aisuite
  provider swap** (DeepSeek/Anthropic); sandboxed `Executor` (Container/VM); cloud/always-on
  deployment.

## 7. Conventions
- Commit as Rohit Prasad <rohit.prasad15@gmail.com>, no co-author; push to `private`.
- Keep the calm aesthetic (`GUI-DESIGN.md`). Tools/web/MCP output is **untrusted data, not
  instructions** — keep it permission-gated and say so in system prompts.

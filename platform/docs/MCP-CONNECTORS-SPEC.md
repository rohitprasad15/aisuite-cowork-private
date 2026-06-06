# MCP & Connectors/Integrations — Spec (draft)

How coworker adds external tools: generic **MCP servers** (bring-your-own) and first-party
**Connectors** (curated integrations with managed auth). Both register tools into the
runtime's `ToolRegistry` and flow through the permission engine. Informed by OpenClaw's
credential architecture (one canonical 0600 store, `${VAR}` refs, PKCE + auto-refresh).

See `HANDOFF.md` for the platform; `PLATFORM-SPEC.md` §9 for the integration thesis.

## 1. Concepts (recap + placement)
| Concept | What | Tool exposure | Status |
|---|---|---|---|
| **Skill** | SKILL.md (prompt + resources) | prompt-level; `load_skill` | done |
| **MCP server** | external tool server, user-configured | tool-level; auto-registered | this spec |
| **Connector** | first-party integration w/ managed auth (Gmail/Calendar/Slack/Telegram/Browser) | tool-level; auto-registered | this spec |

Codex's "Plugins" + "Apps" are merged here into **Connectors/Integrations**. MCP is the
generic escape hatch; Connectors are the curated, one-click experiences.

## 2. The Secret Store (foundation — build first)
A single canonical store; **secrets never enter the model's context, prompts, or traces**.

- **Location:** `~/.config/coworker/secrets.json` (override `$COWORKER_STATE_DIR`).
  **`chmod 0600`**, parent dir `0700`, added to `.gitignore`. (v1 = file perms, matching
  OpenClaw; **upgrade path:** macOS Keychain / age-encryption later.)
- **Shape** — profiles keyed by `connector[:account]`:
  ```json
  {
    "gmail:default":   { "type": "oauth", "access": "…", "refresh": "…", "expires": 1750000000, "account_id": "me@x.com", "scopes": ["…readonly","…send"] },
    "slack:default":   { "type": "token", "bot_token": "${SLACK_BOT_TOKEN}", "app_token": "…" },
    "telegram:default":{ "type": "token", "bot_token": "…" }
  }
  ```
- **Refs not inlines (OpenClaw pattern):** a value may be a literal OR `${ENV_VAR}` →
  resolved from the process env / `~/.config/coworker/.env` at read time. Lets users keep
  secrets in env and the store hold only references.
- **API:** `SecretStore.get(profile) -> dict | None`, `.put(profile, data)`, `.delete`,
  `.status() -> [{profile, type, account, expired}]` (status only — **never returns secret
  values over the REST API**). Reads resolve `${VAR}`. OAuth refresh happens under a
  **file lock**; on expiry, refresh + overwrite (OpenClaw's lifecycle).
- **Injection:** connectors/MCP processes get secrets at **execution time** only (env for
  spawned MCP stdio servers; in-process for native connectors). Tool *results* are scrubbed
  of obvious secret patterns before they re-enter context.

## 3. MCP servers
### Config — standard `mcpServers` JSON
`~/.config/coworker/mcp.json` (global) + `<ws>/.coworker/mcp.json` (workspace, merged;
workspace wins on name clash). Paste-compatible with Claude Desktop / Cursor / Codex.
```json
{
  "mcpServers": {
    "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "${WS}"], "enabled": true },
    "docs":       { "type": "http", "url": "https://…/mcp", "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" }, "enabled": false },
    "db":         { "command": "uvx", "args": ["mcp-server-sqlite", "--db", "./app.db"],
                    "enabled": true, "include_tools": ["query"], "requires_approval": true }
  }
}
```
- `command`+`args` (stdio) or `type:"http"` + `url`+`headers` (remote, streamable-HTTP).
  `${VAR}` resolved from env/secret store. `enabled` flag (UI toggle).
  `include_tools`/`exclude_tools` filter (fights tool-bloat). Optional `requires_approval`
  (default **true** — external). *(Transports: stdio + streamable-HTTP. SSE is not a
  separate transport in the `mcp` SDK's client.)*
### Wiring & lifecycle
- **Own async client on the `mcp` SDK** (NOT aisuite's sync `MCPClient`, which connects on
  its own loop + `nest_asyncio` — fighting our async server). `MCPManager` (in
  `coworker/mcp/`) owns persistent `ClientSession`s, one per server, each in a dedicated
  asyncio task that enters/exits the SDK transport contexts on a single task (anyio cancel
  scopes are task-local). Lazy-connect on the first session that needs a server; close on
  shutdown (lifespan hook).
- Tools map MCP `inputSchema` → OpenAI function schema directly (fidelity); each is wrapped
  as a sync callable that bridges to the live session via `run_coroutine_threadsafe` (so it
  fits the registry's `execute`, which the engine already runs via `to_thread`). Registered
  with `ToolMetadata(category="mcp")`, name-prefixed (`mcp__<server>__<tool>`, OpenAI-safe),
  `requires_approval` per config → permission-gated like any tool.
- Applies to **all agents** (Code + Chat). Config changes apply to new sessions (or a
  `POST /v1/mcp/reload`).
- **Caveat:** every enabled server's tools enter the model's tool array → bloat. Mitigate
  with `include_tools` and by enabling sparingly; per-agent/per-session selection is later.

## 4. Connectors (first-party integrations)
A **Connector** is native code that (a) declares an **auth method**, (b) exposes **tools**
that read credentials from the SecretStore at execution, (c) plugs into the Manage UI for a
one-click connect. Interface:
```python
class Connector(Protocol):
    name: str                      # "gmail"
    title: str                     # "Gmail"
    auth: AuthSpec                 # oauth(provider, scopes) | bot_token | none
    def tools(self, secrets: SecretStore) -> list[ToolFn]: ...
    def setup_url(self, redirect: str) -> str: ...   # OAuth: begin PKCE
    def on_callback(self, params) -> None: ...        # OAuth: exchange + store
```
Registered into the engine's `ToolRegistry` (only if **connected**), `category="connector"`,
sensible per-tool `requires_approval` (reads auto, sends/writes ask).

### The five v1 connectors
| Connector | Auth | Library | Tools (v1) | Default policy |
|---|---|---|---|---|
| **Gmail** | Google OAuth (PKCE, loopback redirect) | `google-api-python-client` | `gmail_search`, `gmail_read`, `gmail_send` | read auto · **send asks** |
| **Google Calendar** | same Google OAuth (shared consent) | `google-api-python-client` | `gcal_list_events`, `gcal_create_event` | read auto · **create asks** |
| **Slack** | Bot token (Socket Mode): `SLACK_BOT_TOKEN`(+`SLACK_APP_TOKEN`) | `slack_sdk` | `slack_search`, `slack_post_message` | read auto · **post asks** |
| **Telegram** | Bot token (BotFather) | `python-telegram-bot` | `telegram_send_message`, `telegram_get_updates` | **send asks** |
| **Browser** | none (local) | `playwright` | `browser_navigate`, `browser_read`, `browser_click` | navigate/read auto · **click/submit asks** |

Notes:
- **Google (Gmail+Calendar) share one OAuth consent** (request both scopes once).
  Loopback redirect (`http://127.0.0.1:<port>/v1/connectors/google/callback`) — no public
  URL needed (local-first). Least-privilege scopes (readonly + the minimum to send/create).
- **Browser** is the heaviest (Playwright + a managed Chromium). It's untrusted-content
  central (web = injection surface) → strict gating + "data not instructions". Could be
  phased last.
- Connectors may *internally* call a mature MCP server instead of an SDK where that's
  cleaner — implementation detail; the managed-auth UX is the point.

## 4a. Messaging connectors & the always-on super-agent (C2)
Slack + Telegram are special: they're **two-way**. Design converged with Rohit; patterns
borrowed from Hermes' `gateway/` (read-only ref at `/Users/rohit/fleet/ro4d/hermes-agent`).

### Outbound (every agent)
A single **`send_message(target, text)`** tool (+ media later). `target` is an opaque handle
(`slack:C123:thread` / `telegram:12345`). Stateless senders read the bot token from the
SecretStore; permission-gated (asks outside Auto). No always-on process needed — any
on-demand Code/Chat session can proactively message ("build done, 3 tests failing").

### Inbound = ONE always-on **super-agent** (no fan-out, no routing table)
Only one agent ever listens, so "which agent handles this message?" disappears.
- **Super-agent** = a persistent, **always-on** agent **based on Cowork** (dedicated system
  prompt later). Its own **workspace**, configured **separately** from the Code/Chat/Cowork
  tabs. *(Cowork isn't built yet → C2 stands up a minimal Cowork agent: workspace-bound
  files/shell/skills + a coworker prompt.)* Other agents get **outbound-only** (send, no
  receive).
- **One continuous thread** (NOT per-chat threads). All inbound from all sources interleave
  into the single thread, each message **tagged with its source + reply-target token**:
  `[Slack DM · Alice | reply→slack:D0…]: <text>`.
- **Queue + steering injection** (reuses the existing `TurnEngine.queue_steering()` /
  `_inject_steering()` seam — no engine surgery):
  - super-agent **idle** → queued message(s) start a `user` turn;
  - super-agent **busy** mid tool-loop → injected at the next loop boundary alongside the
    tool results, so the running agent picks it up **without breaking the agentic loop**.
- **Replies only via `send_message`** — the gateway **never auto-delivers** assistant text
  (plain text = internal reasoning). The agent passes back the reply-target token it
  received. The super-agent's prompt states this explicitly.

### Adapter contract (platform-agnostic, from Hermes)
`BasePlatformAdapter`: `connect() -> bool` (start listener) · `disconnect()` ·
`send(target, text) -> SendResult` · calls `handle_message(MessageEvent)` inbound.
`MessageEvent{text, source, message_id, reply_to}` + `SessionSource{platform, chat_id,
user_id, chat_type, thread_id}` + `SendResult{ok, message_id, error}`.
- **Slack** — **Socket Mode** websocket (`slack-bolt[async]`); tokens `SLACK_BOT_TOKEN`
  (xoxb) **+** `SLACK_APP_TOKEN` (xapp); no public webhook URL (local-first win). Filter
  `user == bot_user_id` + dedup by `ts` (reply-loop guard).
- **Telegram** — **long-poll** `getUpdates` (`python-telegram-bot`; it manages the offset);
  one BotFather token. Outbound: `send_message` with parse→plain fallback.
- Deps **lazy-imported**. **Skip for v1:** mrkdwn/MarkdownV2 conversion, fallback-IP/proxy,
  media/batching, watchdog/heartbeat, pairing, streaming edits, slash commands, multi-
  workspace OAuth.

### Inbound security
**`<PLATFORM>_ALLOWED_USERS` allowlist is the guard** (empty = owner only); checked before a
message reaches the agent. Non-allowlisted consequential tool calls surface an approval at
the TUI/GUI (assume a human is present, first cut); if nobody's watching it waits. "Ask back
in the channel" is the next increment. Inbound content is **untrusted** (data, not
instructions — existing system-prompt guard).

### Always-on / deployment — "one program, three homes"
The gateway runs **inside `coworker-server`** (started in its FastAPI lifespan, next to the
MCP pool). Start manually first; later register autostart — terminal → **Tauri** launch-at-
login (desktop) → always-on **container** (managed cloud sandbox). Same code; only the
supervisor changes. The same always-on process later hosts periodic jobs / cron.

## 5. Manage UI + REST
**Manage screen** (sidebar gear → Manage modal), tabs:
- **Connectors** — a **simple list** of *supported* connectors (Telegram, Slack, Gmail-soon),
  not a gallery. **Guided token wizard** (chosen over managed OAuth — see below):
  - **descriptor-driven** (`connectors/descriptors.py`): each connector declares `auth`,
    `fields` (label/secret/help/placeholder), step-by-step `instructions`, and a `validate`
    (a real API call). The UI renders the wizard generically from the descriptor → adding a
    connector is data, not UI code (mirrors Hermes' setup wizard).
  - **validate-on-connect:** paste the token → server calls `getMe` / `auth.test` → shows the
    bot identity back ("Connected as @yourbot") or the real error.
  - **chat-ID auto-capture** (lands with inbound): DM the bot, then "Capture" fills the
    allowlist — instead of "go find your ID".
  - **Why guided, not one-click OAuth:** we're OSS/local-first (can't ship an OAuth client
    secret, no central callback host), and Telegram has no OAuth + Slack Socket Mode needs a
    user-made app token regardless. Descriptor/REST are shaped so a **managed one-click OAuth
    drops in later for the cloud product** (`auth="oauth"`) with no data-model change.
- **MCPs:** list servers, toggle `enabled`, **+ Add** (paste JSON), view each server's tools.
- **Skills:** list catalog, enable/disable, create *(later)*.

**REST:**
- `GET /v1/mcp` · `POST /v1/mcp` · `PATCH /v1/mcp/{name}` · `DELETE /v1/mcp/{name}` ·
  `GET /v1/mcp/{name}/tools` · `POST /v1/mcp/reload`.
- `GET /v1/connectors` (descriptors + status, **no secrets**) ·
  `POST /v1/connectors/{name}/connect` (validate → store) · `POST …/{name}/disconnect`.
  *(Managed OAuth later adds a redirect/callback variant of connect.)*
- Secrets are **never** returned by any endpoint (status + public bot identity only).

## 6. Security model
- **Secrets out of context**: never in prompts/traces/tool args; injected at execution;
  results scrubbed. Store `0600`, gitignored.
- **External = untrusted**: MCP + connector + web output is data, not instructions
  (system-prompt guard already present). `requires_approval` defaults to true for external
  tools; sends/writes/clicks always ask outside Auto mode.
- **Least privilege**: minimal OAuth scopes per connector; per-connector enable.
- **Lifecycle**: auto-refresh under file lock; clear "expired → reconnect" status.
- Ties to the §8 `Executor` sandbox boundary (HANDOFF) for MCP stdio subprocesses later.

## 7. Build phases
New runtime deps are **lazy-imported / optional** per connector (Playwright opt-in) so the
base install stays light. C1 adds the `mcp` package (used by our own async client).
- **C0 — SecretStore** (foundation): file store (0600, `${VAR}` resolution, status).
  `coworker/secrets.py`. **DONE** (7 tests).
- **C1 — MCP**: `mcp.json` loader (global+workspace), **own async `MCPManager`** on the `mcp`
  SDK, filtered registration + permission-gating, `/v1/mcp*` REST, MCPs tab. *(No key needed.)*
  **DONE** (backend + 7 tests + live filesystem-server smoke; GUI tab next.)
- **C2 — Messaging connectors (Slack + Telegram)** — see §4a. Build order:
  1. **Shared core** — **DONE** (`connectors/`): adapter contract + `MessageEvent`/
     `SessionSource`/`SendResult` + gateway + `send_message` tool (every agent).
  2. **Minimal Cowork agent** — **DONE** (`agents/cowork.py`).
  3. **Super-agent + inbound** — **DONE**: `SuperAgent` (one thread, queue + steering via the
     engine seam, replies only via `send_message`); real Telegram (long-poll) + Slack (Socket
     Mode) adapters (lazy-imported `[messaging]` extra); allowlist; wired into the server
     lifespan (`manager.start_gateway`). *First-cut permission: the super-agent auto-allows
     `send_message` + reads; writes/shell still need approval (no inbound approver yet) →
     "ask in channel" is the next increment.*
  4. **Connector connect UI + Super-agent config** — **DONE**: guided connect wizard (§5);
     a **Super-agent** tab (workspace get/set, listening status, per-connector allowlist) +
     **chat-ID auto-capture** — the gateway records recent senders (identity only, in-memory,
     capped) so you DM the bot and click **Allow** instead of hunting for your numeric ID;
     allow/disallow update the live gateway with no restart. `/v1/superagent`,
     `/v1/connectors/{name}/allow|disallow`.
  5. **GUI super-agent surface** — **DONE**: the super-agent now runs always (even with no
     connector) and has a first-class **Assistant** tab. A `/ws/superagent` stream broadcasts
     its engine events so the GUI shows the **one continuous thread live** (incoming
     Telegram/Slack messages tagged, its replies, tool activity); you can **message it from
     the GUI** (local owner, allowlist-bypassed, answered in plain text). **Approvals now
     work in the GUI**: risky tools prompt the surface when a client is watching, and stay
     denied when nobody is — this resolves the inbound-approval caveat *for the at-desk case*.
  Deferred (door left open): fan-out, "ask back in channel" (over Telegram/Slack), autostart
  registration, cron.
- **C3 — Google OAuth**: PKCE + loopback callback + refresh; **Gmail + Calendar**.
- **C4 — Browser** (Playwright): heaviest; strict gating.

## 8. Decisions (RESOLVED)
1. **Connectors native, not blessed-MCP** — native code owns auth + tools; MCP stays the
   generic escape hatch. ✓
2. **Secret-at-rest = `0600` file for v1**, behind the `SecretStore` interface; OS
   Keychain / age-encryption is a later swap behind the same API. ✓
3. **Build order: C0 → C1 → C2 (Telegram+Slack) → C3 (Google: Gmail+Calendar) → C4
   (Browser).** Key-free phases first. ✓
4. **New runtime deps lazy-imported / optional** (`google-api-python-client`, `slack_sdk`,
   `python-telegram-bot`, `playwright`); base install stays light. C1's `mcp` is a base dep. ✓
5. **MCP client: our own async layer on the `mcp` SDK**, not aisuite's sync `MCPClient`
   (async fit, clean lifecycle, our own schema/metadata mapping). ✓ (see §3)

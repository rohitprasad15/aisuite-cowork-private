# GUI Backlog — improvements (from Claude Cowork "Code" tab inspiration)

Captured from Cowork Code-tab screenshots. **Borrow the capability, not the look.** Ordered
by impact. The current GUI is a thin client of the server (one workspace per server launch).

## P0 — the real blocker

### 1. In-GUI workspace / folder picker  ← build this next
Today the workspace is fixed at `coworker-server --cwd <dir>`; you must relaunch to switch.
Cowork shows a **working-directory bar** above the composer:
- a folder chip with a dropdown: **Recent folders** list + **"Open folder…"** (native picker).
- **Local** (vs remote) indicator; **git branch** chip (e.g. `release-2026-02-28`); **worktree** chip.
- **"Add another folder"** → multi-root workspace.

**Backend implications (non-trivial):** workspace must become **per-session**, not
per-process. Needs:
- server API to set/switch a session's workspace (and list recent workspaces).
- engines keyed by (session, workspace); the `code` skill + permission root rebind per workspace.
- a folder-open mechanism — in the browser this needs a backend `GET /v1/fs/folders` +
  manual path entry; the **Tauri** build can use the native folder dialog.
- git branch / worktree detection per folder (we already have a read-only git toolkit).

## P1 — session & history

### 2. ✅ DONE — Recents replay transcript + titles
Sessions are now named (first user message) and clicking replays history
(`GET /v1/sessions/{id}/messages`). Workspace paths canonicalized (realpath) +
migration. **Remaining:** cross-project grouping — Codex groups sessions under
folder/project headers in the sidebar ("Projects"); ours only lists the *current*
workspace. Show all recent workspaces as collapsible folder groups.

### 3. Permissions menu (Codex-style; decided)
Replace the mode pill with a proper dropdown. Mapping (decided with Rohit):
- **Ask for approval** → `interactive` (default; ask on edits/commands).
- **Full access** → `auto` (unrestricted).
- **Custom (config.toml)** → fine-grained allow/ask rules from config (extend config
  beyond `allowed_commands` to per-tool/per-path rules).
- **Plan** → `plan` (read-only) — keep as a 4th option.
Defer Codex's *"Approve for me"* (auto-approve safe, ask on unsafe) — needs an
unsafe-action classifier; `Custom` covers most of the need. Add ⌘M + number shortcuts.

## P2 — polish & affordances

### 4. Code-tab home dashboard
Cowork home: greeting **"What's up next, <name>?"** + an **overview card** — Sessions,
Messages, Total tokens, Active days, current/longest streak, peak hour, favorite model, an
**activity heatmap**, with **All / 30d / 7d** filters. We already capture trace data
(aisuite tracing) to source much of this. Nice-to-have, not core.

### 5. Composer affordances
- **Model picker** + **reasoning-effort** selector (Low/Med/High) in the composer bar.
- **"+"** attach (files/images) and **mic** (voice) — later.

### 6. Sidebar nav
- **Routines** → scheduled/background agents (our Slice-2 scheduler, P11-ish).
- **Customize** → skills/commands management; **More**.
- **Account** block at bottom (avatar, plan, update banner).

## Notes
- Items 1 & 3 need **server/runtime** changes (per-session workspace; an "accept-edits"
  permission nuance), not just front-end.
- Keep the calm aesthetic from `GUI-DESIGN.md`; these add capability, not clutter.

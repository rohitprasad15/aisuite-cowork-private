# GUI Design Notes (inspiration)

> Reference: a Claude Cowork screenshot the user shared. **Do not mimic it** — borrow the
> *aesthetic principles* and the *spatial division*, then make our own (code-focused) take.

## What to borrow (the user explicitly likes these)
- **Clean, calm, minimal.** Generous whitespace; nothing dense or enterprise-y. Light,
  off-white canvas with a *very* subtle dot-grid texture in the main area.
- **Clear two-pane division:** a quiet left sidebar (navigation/sessions/account) vs. a
  spacious main content area. The split is the backbone of the layout.
- **Sidebar structure:** segmented tab switcher at top (Cowork shows Chat / Cowork /
  Code); a short list of primary items with simple line icons; a "Recents" section;
  account/status pinned to the bottom.
- **Main area focal point:** an elegant **serif** headline greeting, then a single
  prominent **rounded input card** as the hero, with affordances (＋, mic) inset; a row of
  contextual controls *below* the input (project, mode, model picker); and a short list of
  suggested actions with icons underneath.
- **Type:** serif for headlines (warm, editorial), clean sans for body/UI. Subtle hairline
  dividers, soft shadows, rounded corners.

## What to avoid
- Don't copy Cowork's exact nav items, copy, the asterisk mark, or color accents.
- Don't replicate its knowledge-work framing — ours is a **coding coworker**.

## Our adaptation (code-focused)
- **Left sidebar:** surface/skill switcher (Code now; Chat later); **session list**
  (Recents → our `--resume` sessions); current **workspace**; status (model · mode) and
  account at the bottom.
- **Main area, idle:** serif greeting + a hero input card; below it a control row with
  **workspace**, **mode (plan/interactive/auto)**, and **model** pickers; a few starter
  prompts ("run the tests", "summarize this repo", "fix the failing build").
- **Main area, in a turn:** conversation transcript with **inline tool calls** and
  **diffs**; an **approval card** inline (or a calm modal) for permission requests; a
  right-hand **todo panel** that fills in as the agent plans. Keep it calm — tool activity
  is collapsible, not a wall of logs.
- **Palette:** off-white/paper canvas, ink-near-black text, one restrained accent; risk
  signaling (approval) via a single warm accent, not alarm-red everywhere.

## Stack (locked)
React (TypeScript) SPA + Tauri shell + Python runtime as a sidecar; the UI is a thin
client of the local OpenAI-compatible server + WS event stream (P6). See PLATFORM-SPEC §10.

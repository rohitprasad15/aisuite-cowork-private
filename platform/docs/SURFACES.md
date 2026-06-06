# Surfaces — Chat · Code · Cowork · MyHelper

How the product is organized for the user. Decided with Rohit (see the "Decisions" log at the
bottom). Supersedes the earlier loose use of "Cowork" to mean both a surface and the
super-agent.

## The shape: 3 session surfaces + 1 persistent helper

There are **two kinds** of surface:

- **Session surfaces — Chat, Code, Cowork.** You *spin up an agent to do a thing*. Sessions
  are **ephemeral and many**; GUI-only. Disposable problem-solvers.
- **The persistent helper — MyHelper (the super-agent).** Your **one** always-on personal
  assistant. **Persistent, single continuous thread**, long-term memory, reachable from the
  GUI **and** over Telegram/Slack. Not disposable — it's "you have a coworker."

| Surface | What it is | Lifetime | Workspace | Reached via |
|---|---|---|---|---|
| **Chat** | quick Q&A, brainstorming | ephemeral, many | none | GUI |
| **Code** | work *in* a codebase | ephemeral, many (per repo) | a repo (required) | GUI |
| **Cowork** | solve an isolated problem → produce a deliverable | ephemeral, many | a scratch/output folder | GUI |
| **MyHelper** | your one always-on personal helper | **persistent, single thread** | its own dedicated workspace | GUI + Telegram/Slack |

## Code vs Cowork — the key distinction
Both are workspace-bound and have files + shell; the difference is **framing + emphasis**, not
plumbing:
- **Code** = you're a developer editing a codebase. Workspace *is* a repo. Leans on git,
  precise diffs, run/build/test. Coding-centric prompt.
- **Cowork** = you're a knowledge worker producing a **deliverable** — a research memo, an
  analysis, a plan, a data pull, a small script. Workspace is a scratch/output folder. Tools
  are **general** (read/write files, shell, web, skills) with an **outcome-oriented** prompt;
  **not** git-centric.

## MyHelper specifics
- **Singular & always-on.** One instance, persistent single thread, long-term memory; runs in
  the always-on server. (Built; lives behind the GUI **MyHelper** tab + `/ws/superagent`, and
  over connected Telegram/Slack.)
- **Its own system prompt**, separate from Cowork — even if they look similar at first. (Cowork
  = task executor; MyHelper = persistent personal assistant.)
- **Naming is personal.** Default "MyHelper"; let the user **rename** it (a setting and/or an
  **onboarding step** that suggests names and lets them personalize).
- **Permissions:** auto-allows replying + reading; risky tools prompt the GUI when watched,
  else denied. ("Ask in the channel" over Telegram/Slack is a later increment.)
- **Future — orchestration:** MyHelper should be able to **spin off a Cowork session** for a
  big task ("go build this and report back"), and **spin off a headless Code agent** when
  needed. Start simple; add later.

## Build priority (agreed)
1. **Improve Code and Cowork first** — ✅ **un-collapse done**: Cowork is now a real session
   surface (own `cowork` agent + sidebar tab, project-grouped like Code); MyHelper has its own
   `myhelper` agent + prompt (renameable via the Super-agent tab) and the GUI tab reads its
   name; **web search** added for every agent. Next: document generation, PDF read, more.
2. **Then come back to improve MyHelper.**

## Capability vision (inspired by Claude Cowork)
What an outcome-oriented coworker (Cowork, and ultimately MyHelper) should be able to do.
Status: ✅ have · 🟡 partial · ⬜ roadmap.

- **Files & Documents** — read/write files ✅; create/edit Word/PDF/Excel/PowerPoint ⬜;
  read+summarize uploads 🟡 (text ✅, PDF parse ⬜).
- **Research & Writing** — drafting (emails/reports/posts) ✅ (LLM); **web search** ✅
  (`web_search` tool; keyless DuckDuckGo default + configurable Tavily/Brave via
  `web_search:default` secret / `web_search_provider` config; `/v1/web-search`).
- **Code & Data** — write/debug/explain code ✅; run scripts ✅ (persistent shell,
  `LocalExecutor`); **isolated Linux sandbox** ⬜ (Container/VM executor behind the existing
  `Executor` boundary).
- **Computer & Desktop** — browser control ⬜ (C4, Playwright); native desktop control ⬜ (later).
- **Automation** — **scheduled tasks / cron** ⬜; live dashboards ⬜. Runs in the always-on
  process (the one hosting MyHelper's gateway).
- **General** — Q&A, brainstorm, planning ✅.
- **Connectors** — MCP tools ✅ (C1); Telegram/Slack ✅ (C2); Gmail/Calendar ⬜ (C3); Browser ⬜ (C4).
- **Skills** — Anthropic SKILL.md, progressive disclosure ✅ (any surface can load).

### Scheduling / automation — design note (from Claude Cowork)
Claude Cowork exposes three tools; mirror this shape later:
- `create_scheduled_task` — a **cron expression** (`0 9 * * 1` = Mon 9am) **or** a one-time
  `fireAt` datetime + the prompt/task to run.
- `list_scheduled_tasks` · `update_scheduled_task`.
When a task fires, the agent **runs the same work it would in chat** (search, call tools,
generate files) and **delivers the result** (via MyHelper's messaging or the GUI). This is the
natural payoff of the always-on process — same home as the gateway; pairs with autostart.

## Decisions log
- **2026-06-05:** Four surfaces confirmed — **Chat, Code, Cowork, MyHelper**. Cowork is its
  own ephemeral-session surface (outcome/deliverable-oriented, general tools, not git-centric),
  distinct from Code. MyHelper is the singular always-on helper (own prompt, renameable,
  GUI+messaging). MyHelper will later spin off Cowork/Code sessions. Build Code + Cowork first,
  then MyHelper. "Assistant" tab → rename **MyHelper**; bring back **Cowork** as a real surface.
  Capability vision captured from a Claude Cowork session (documents, web search, sandbox,
  desktop, scheduling).

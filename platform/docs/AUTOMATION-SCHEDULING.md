# Automation / Scheduling — design + status

**STATUS: BUILT (v1).** Backend `coworker/automation/` (models · SQLite `TaskStore` ·
`Scheduler` tick loop · create/list/update/delete tools for Cowork+MyHelper · REST
`/v1/automations`), scheduler started in the server lifespan, run-once-catch-up + skip-on-
overlap, approve-at-creation + per-task always-allowed, deliver to the task's own thread +
notify. GUI **Scheduled** view (list + task detail: instructions, schedule, history, Run-now,
toggle, delete). Verified live: a task ran the real Cowork agent → web search → wrote a
deliverable file → recorded the run. Remaining polish: a richer confirm *card* (v1 uses the
generic approval), live artifacts, desktop keep-awake.

---


Inspired by Claude Cowork's scheduled tasks (`create/list/update_scheduled_task`, cron or
one-time `fireAt`). This is a **design to react to**, not final. Open decisions are flagged
**[D#]** at the bottom — that's the part to chew on.

## 1. The idea
A **scheduled task** = a saved instruction + a schedule + where to deliver the result.
When it fires, the system **runs the same agent work it would in a chat** and delivers the
output. It's the natural payoff of the always-on server (the one already hosting MyHelper's
gateway) — the scheduler lives in that process so it runs whether or not the GUI is open.

Flow:
```
user (in a Cowork session): "every weekday at 7am, summarize my unread Slack and email me"
  → agent calls create_scheduled_task(prompt=…, schedule=cron "0 7 * * 1-5",
                                       origin=<this cowork session>, delivery=…)
  → stored + next_run computed
  ... time passes ...
  → scheduler sees it's due → runs an agent turn with the prompt in the right workspace
  → delivers the result (see §4) → records the run
```

## 1a. What the Claude Cowork screenshots settle (2026-06-05)
Two reference screenshots refined several calls:
- **Creation = agent proposes → user confirms a card.** "setup an automation … briefing at
  7:10pm everyday" → the agent calls `create_scheduled_task`, which renders a **confirmation
  card**: title, **human-readable** schedule ("Every day at 7:10 PM"), a **Details** expander,
  extra settings (`notifyOnCompletion: true`), and **Schedule / Cancel**. → This *is*
  **approve-at-creation** (resolves **[D3]**) and reuses our approval flow as a rich card.
- **UI home = a "Scheduled" section under the Cowork surface** (resolves **[D7]**). Task
  cards show a schedule pill ("Every day at **~**7:10 PM" — note `~`: tick-based, approximate).
- **Two creation paths + run-on-demand:** natural language → the tool, **and** a `/schedule`
  slash command inside an existing session; tasks can also be **run now** ("…or whenever you
  need them"). 
- **The awake/always-on reality:** "Scheduled tasks only run while your computer is awake" +
  a **Keep awake** toggle. For us: tasks run **while `coworker-server` is up**; the desktop
  build offers keep-awake; the cloud build is truly always-on. Surface this honestly + apply
  the missed-run policy **[D4]** for downtime.
- **`notifyOnCompletion`** is a per-task delivery flag → folds into `Delivery`.

## 1b. Execution model — a task is its own thread (from the run screenshots)
The decisive insight: **a scheduled task is its own persistent entity with its own thread**,
*separate from the chat that created it* (it shows under "Scheduled" as e.g. "Daily news
briefing", not in the origin chat). Concretely:
- The task stores rich **Instructions** (the prompt), **Repeats** (schedule), an **Active**
  toggle + **Next run**, **Run now**, and a per-task **Working folder** for artifacts.
- Each fire is a **Run**: a **fresh execution of the Instructions** (the model re-does the
  work each time — fresh context + long-term memory, *not* a growing conversation), appended
  to the task's thread and listed in a **Runs / History** panel (with an unread dot).
- A run surfaces **Progress** (its todo checklist), the tool work, the final output **in the
  task thread**, and any **artifact files** in the working folder
  (`daily-briefing-2026-06-05.md`). Delivery = it lands in the task thread (a "1 new" badge)
  + optional notify.
- **Permissions: approve-at-creation + a growing per-task "Always allowed" set.** Approvals
  you grant during a run are remembered for that task ("Approvals you grant during a run
  appear here") and auto-applied next time. Maps onto our `session_allow_tools` /
  `session_allow_commands`, persisted per task.

→ This **resolves [D1]** (deliver to the task's own thread + notify), **[D2]** (fresh
execution per run, in the task's dedicated thread — not the origin chat), and **[D8]** (final
text + artifacts + progress, recorded per run), and **refines [D3]**.

## 2. Data structures (sketch)
Persisted in SQLite (reuse `coworker.db`: a `scheduled_tasks` table + a `task_runs` history
table) so they survive restarts.

```python
@dataclass
class Schedule:
    kind: Literal["cron", "once"]
    cron: Optional[str] = None        # "0 9 * * 1"  (recurring)
    fire_at: Optional[str] = None     # ISO datetime (one-time)
    timezone: str = "UTC"             # cron is tz-sensitive — store it explicitly

@dataclass
class Origin:                         # WHERE it was launched from — a reference, not the home
    surface: str                      # "cowork" | "myhelper" | "code" | "chat"
    session_id: str                   # the conversation that created it
    chat_target: Optional[str] = None # if created over messaging: "telegram:123" / "slack:C1"

@dataclass
class Delivery:                       # WHERE results go (can be several)
    to_task_thread: bool = True       # primary: the task's OWN thread (a "1 new" badge)
    notify_on_completion: bool = True  # the per-task "tell me when it's done" flag
    notify_myhelper: bool = False     # also drop a note in MyHelper's thread
    to_chat: Optional[str] = None     # also push to a messaging target ("telegram:123")

@dataclass
class ScheduledTask:
    id: str
    title: str                        # short human label ("Daily news briefing")
    instructions: str                 # the rich prompt the run executes each time
    schedule: Schedule
    origin: Origin
    delivery: Delivery
    task_session_id: str              # the task's OWN persistent thread (runs accumulate here)
    workspace: str                    # working folder for run artifacts
    agent: str = "cowork"             # which agent runs it
    model: Optional[str] = None       # optional override
    always_allowed_tools: list[str] = ...   # grows from approvals granted during runs ([D3])
    always_allowed_commands: list[str] = ...
    enabled: bool = True              # the Active toggle
    created_at: str = ...
    updated_at: str = ...
    next_run: Optional[str] = None    # computed; shown as "~7:10 PM"
    last_run: Optional["TaskRunSummary"] = None
    run_count: int = 0
    max_runs: Optional[int] = None    # one-time = 1; or "run N times"

@dataclass
class TaskRun:                        # history / audit (one row per execution)
    run_id: str
    task_id: str
    started_at: str
    finished_at: Optional[str]
    status: Literal["ok", "error", "skipped", "running"]
    result_text: Optional[str]        # the agent's deliverable (or a summary)
    artifacts: list[str]              # files written, if any
    delivered_to: list[str]           # where it landed
    error: Optional[str] = None
```

## 3. The scheduler (runtime)
- Lives in the **always-on server** (`SessionManager`), started in the FastAPI lifespan next
  to the gateway/MCP. One background task.
- **Awake/always-on reality (from the screenshots):** tasks only fire **while
  `coworker-server` is running**. Three homes: desktop = while the app/computer is awake
  (offer a "Keep awake" toggle later; warn in the UI like Cowork does); cloud sandbox =
  truly always-on; bare server = while the process/service is up. Show next-run + a clear
  "runs while coworker is on" note. Downtime → missed-run policy **[D4]**.
- **Tick model:** wake every ~30–60s, find tasks whose `next_run <= now`, run them, recompute
  `next_run` (cron resolution is 1 min, so a minute tick is plenty). `fire_at` one-shots are
  handled the same way; after firing, `enabled=False` (or `run_count>=max_runs`).
- **Cron math + tz:** use `croniter` (small dep) for next-fire computation; honor
  `schedule.timezone`. Avoid hand-rolling cron.
- **Restart / downtime — missed runs:** on startup, recompute `next_run`; for runs missed
  while the server was down, policy options in **[D4]** (skip / run-once-catch-up / run-all).
- **Overlap:** if a task's previous run is still going when it's due again → **skip** this
  tick (don't stack), record `skipped`. **[D6]**
- **Concurrency cap:** a small semaphore (e.g. 2–3 concurrent task runs) so a burst of due
  tasks doesn't swamp the box.
- **Execution:** build an engine for `task.agent` in `task.origin.workspace` (reuse
  `SessionManager`), run one turn with `task.prompt`, collect the final text + any artifacts.

## 4. Delivery — the interesting part (your point)
A task created **in a Cowork session** should be able to deliver back **to that
conversation**, not only to MyHelper. So `Delivery` supports multiple sinks, and `Origin`
records the requesting session. Three sinks, combinable:

1. **`to_origin_conversation`** — append the run's result to the **origin session's
   transcript** (via `ConversationStore`). When the user reopens that Cowork session, the
   scheduled results are there inline, in context. *Best for "this conversation's recurring
   task."* If a GUI client has that session open, push it live over the WS too.
2. **`to_chat`** — deliver over a messaging target (`telegram:…` / `slack:…`). Used when the
   task was created over messaging, or the user wants it pushed somewhere.
3. **`notify_myhelper`** — drop a short note into **MyHelper's** always-on thread ("✓ ran
   *Morning digest* — 3 items, see Cowork session X"). Because MyHelper is the surface the
   user actually watches, this is the reliable "it happened" signal even if the origin
   session is buried.

**Resolved (§1b):** the durable home is the **task's own thread**, not the ephemeral origin
chat — so the original "deliver to the requesting Cowork session" concern is solved by giving
the task its *own* persistent thread under the **Scheduled** view, where every run accumulates
(with a "1 new" badge). `notify_on_completion` adds the nudge (and `notify_myhelper` / `to_chat`
can fan it out). The origin is kept only as a launch reference. **[D1] ✓**

## 5. Execution context — RESOLVED (§1b)
**A task has its own dedicated, persistent thread** (`task_session_id`), separate from the
origin chat. Each fire is a **fresh execution of `instructions`** (fresh context + long-term
memory — the model re-does the work, doesn't continue a growing conversation), recorded as a
**Run** appended to the task thread (a Runs/History list). So: fresh per run, persistent home.
Not the origin conversation; not throwaway.

## 6. Surfaces (UI)
- **Creation = propose → confirm a card** (from the screenshots). The agent calls
  `create_scheduled_task` (it converts NL like "7:10pm everyday" → cron + a human-readable
  label and fills `origin`); that surfaces a **confirmation card** — title, "Every day at
  7:10 PM", a **Details** expander (prompt/cron/delivery), settings (`notify_on_completion`),
  and **Schedule / Cancel**. The task is created only on **Schedule** (this is the
  approve-at-creation gate, **[D3]**). Reuses the engine's approval flow, rendered richly.
- **Two creation paths + run-now:** natural language → the tool, **and** a **`/schedule`**
  slash command inside an existing session. Every task also has **Run now** (on-demand).
- **Agent tools:** `create_scheduled_task`, `list_scheduled_tasks`, `update_scheduled_task`,
  `delete_scheduled_task` (and a run-now path). Available to **Cowork + MyHelper** **[D5]**.
- **"Scheduled" view under Cowork** (**[D7]**, per the screenshot): a section in the Cowork
  surface listing task cards — title, description, schedule pill ("Every day at ~7:10 PM"),
  enabled toggle, last result, run history, Run-now. The durable home for results + mgmt.
- **REST:** `GET/POST/PATCH/DELETE /v1/automations` + `POST /v1/automations/{id}/run` +
  `GET /v1/automations/{id}/runs`.

## 7. Permissions for unattended runs
Scheduled runs execute with **no human watching** — same issue as inbound MyHelper. A task
that writes files / sends messages / runs shell is consequential. Options **[D3]**:
- **(a)** Restricted: reads + produce-a-deliverable in the workspace; destructive/external
  actions denied.
- **(b)** Approve-at-creation: when the task is created, the user OKs its capability envelope
  ("this task may: write files, send Slack") once; runs stay within it.
- **(c)** Auto within workspace (path-scoped writes ok; shell/external still gated).
**Resolved → approve-at-creation + a growing per-task "Always allowed" set** (the screenshots
confirm both): you consent to the standing automation when you click **Schedule**; then, if a
run wants something not yet permitted, it can request approval, and **approvals you grant
during a run are remembered for that task** ("Always allowed") and auto-applied next time.
Persist `always_allowed_tools`/`always_allowed_commands` per task; on each run, seed the
engine's session-allow lists from them. Creating the task is itself the consequential,
approved action. (When unattended and a *new* approval is needed, the run pauses/defers that
step and surfaces it for next time — never silently does it.)

## 8. Dependencies
- `croniter` (cron next-fire math) — small, pure-python. Lazy/optional is fine but it's tiny.
- No external service. Storage = existing SQLite.

## 9. Minimal v1 vs full vision
- **v1:** SQLite task store; a 60s tick scheduler in the always-on server; cron + `fire_at`;
  `create/list/update/delete` tools; deliver to **origin conversation + MyHelper note**;
  approve-at-creation permissions; a basic **Automations** list in the GUI. Skip-on-overlap;
  skip-missed-on-downtime.
- **Later:** live dashboards, catch-up policies, richer delivery routing, per-task model/mode,
  multi-step/workflow tasks, "run now" + dry-run, calendars/natural-language schedules.

## Open decisions
**Resolved by the 2026-06-05 screenshots:**
- **[D1] Delivery → the task's own thread** (a "1 new" badge) + `notify_on_completion`. ✓
- **[D2] Execution → fresh run each fire, in the task's own dedicated thread** (not origin). ✓
- **[D3] Permissions → approve-at-creation + a growing per-task "Always allowed" set.** ✓
- **[D5] Who can schedule → Cowork + MyHelper.** ✓
- **[D7] UI home → a "Scheduled" section under Cowork** (task list + task detail: Instructions,
  Repeats, History, Run-now, Active, Next run, Always-allowed). ✓
- **[D8] Result → final text + working-folder artifacts + a progress checklist, per run.** ✓
- *(new)* Each task = its **own thread**; creation = **propose→confirm card**; **`/schedule`**
  + **Run now**; schedule shown human-readable with `~`; **awake/always-on** caveat surfaced.

**Still open (small — I have leans):**
- **[D4] Missed runs on downtime** — skip / run-once-catch-up / run-all. (Matters more on
  desktop given the awake caveat.) *Lean: run-once-catch-up.*
- **[D6] Overlap** — skip vs queue when a run is still going at next fire. *Lean: skip.*

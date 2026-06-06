# aisuite-code vs SPEC — Gap Analysis

Comparing the existing reference CLI (`aisuite-agent-framework/cli/py/aisuite-code-cli`)
against `SPEC.md`, to decide: **extend it** or **build new + harvest**.

## The load-bearing divergence

`aisuite-code` is built **on `ai.Runner.run_sync` / `continue_sync`**, which delegates
the whole agentic loop to aisuite's **blocking `max_turns`** runner in `client.py`.
Our spec's #1 decision was to **own the loop** (async engine + event bus, aisuite only
for single-shot completions). That one difference invalidates the CLI's entire spine:
the control flow, the (lack of) async, and the post-hoc rendering all hang off `Runner`.

Concretely: `app.py` calls `run_sync(...)`, which runs *all* iterations of a turn and
returns only at the end; `print_steps()` then renders history **after the fact**. There
is no per-iteration rendering, no interruption, and no steering — and there can't be
without replacing the spine.

## Gap table

| Spec area | aisuite-code today | Status | Notes / effort |
|---|---|---|---|
| Own async turn engine (§5) | Uses `ai.Runner` blocking loop | ❌ Missing | Spine replacement — the core build |
| Event bus / event model (§5) | `print()` after `run_sync` returns | ❌ Missing | New; enables TUI + interrupt |
| Interruption (ESC) + steering | Blocking `readline` → blocking run | ❌ Missing | Depends on owned loop |
| Streaming | None | ✅ Match (deferred) | Both defer |
| `ModelClient` (no-`max_turns`) (§4) | Goes through Runner w/ `max_turns` | ❌ Opposite | New thin adapter |
| Textual TUI (§14) | Plain stdin/stdout, no Rich | ❌ Missing | Whole UI layer is new |
| `files` toolkit (§6) | `ai.toolkits.files(allow_write)` | ✅ Reuse | Same dependency |
| `git` toolkit (§6) | `ai.toolkits.git` read-only | ✅ Reuse | Same |
| Persistent shell (§8) | `ai.toolkits.shell` = per-call `subprocess.run` | ❌ Missing | New component; `Executor` boundary |
| `todo`/plan tool (§6) | None | ❌ Missing | New, small |
| Reviewer subagent | Has `agent_tool` reviewer | ➕ Ahead | Spec defers subagents; nice-to-have |
| Permission modes Plan/Normal/Auto (§7) | Normal-only; `--read-only` removes write tools | ⚠️ Partial | No live Plan/Auto modes |
| Permission rules (path/command scoping) (§7) | `requires_approval` flag + exact-command memory | ⚠️ Partial | No path scoping / rule layer |
| Permission memory scopes (§7) | Session only (`always_allow_*`) | ⚠️ Partial | No project-config persistence |
| Approval prompt UX | `ApprovalController` — good content | ✅ Harvest | Port the prompt design |
| Denial → tool error to model | Returns `allowed=False` decision | ✅ Match | Via aisuite policy path |
| Context management (§9) | None (history just grows) | ❌ Missing | Token track / dedup / `/compact` |
| Sessions: resume across restarts (§10) | In-memory `self.result`; `/clear` | ❌ Missing | No `/resume`, no `--continue` |
| Checkpointing | None | ✅ Match (deferred) | Both defer |
| AGENTS.md ingestion (§11) | Hardcoded instructions in `agent.py` | ❌ Missing | New; root + global |
| Built-in slash commands (§12) | `/help /status /viewer /last /clear /exit` | ⚠️ Partial | Missing `/mode /model /context /compact /resume /init` |
| User-defined slash commands (§12) | None | ❌ Missing | New `.md` command system |
| Tracing sinks + viewer (§13) | `LocalTraceSink` JSONL + HTTP + viewer | ✅ Reuse | Strength — keep as-is |
| Artifact store (§8 large output) | `FileArtifactStore` | ✅ Reuse | Strength — keep |
| Config: `.harness/config.toml` (§15) | argparse flags only | ❌ Missing | New config file |

## Reusable vs replace

**Reuse directly (framework-level, dependency either way):**
- `aisuite.toolkits.files`, `aisuite.toolkits.git`
- `aisuite.tracing` sinks + viewer
- `aisuite.FileArtifactStore`

**Harvest as reference (port the ideas, not the wiring):**
- `approval.py` — the approval prompt content (action/risk/effect/preview, y/n/a/c) is
  genuinely good; reimplement against our event bus / Textual modal.
- `agent.py` — the system-prompt guidance on when to use `replace_in_file` vs
  `apply_patch` vs `write_file`.
- `rendering.py` — the tool-argument/result summarization logic for inline display.

**Replace entirely (spine — tied to `Runner` + blocking + print):**
- `app.py` (session loop), `main.py`, `config.py` (flags-only), the `Runner`-based
  `_run_agent` path. None of this survives the "own the loop" decision.

## Recommendation

**Build new, harvest aggressively.** ~3 framework modules reuse as a dependency, ~3 CLI
modules are worth porting for their *content*, but the harness *skeleton* (loop, async,
event bus, Textual) is a from-scratch build because the existing one is structured
around `ai.Runner` — the exact layer the spec replaces.

"Modify in place" would mean ripping out `app.py`'s spine while keeping the package
shell, which is more friction than starting clean in `coding-agent-harness/` and
importing/porting the good parts. The reusable bits are reusable *regardless* of which
repo they live in, so a fresh package loses almost nothing and avoids inheriting the
`Runner`-shaped control flow.

**Net:** a new package, depending on `aisuite-agent-framework` for toolkits/tracing/
artifacts, porting `approval`/`agent`/`rendering` logic, and building the loop +
ModelClient + permission engine + context manager + Textual UI fresh per `SPEC.md` §16.

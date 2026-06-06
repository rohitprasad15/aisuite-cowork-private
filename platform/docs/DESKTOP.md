# Desktop app (Tauri) — macOS dev build

The desktop app is a **Tauri v2** native window over the existing React SPA
(`surfaces/gui`). Tauri manages the Python `coworker-server` as a **sidecar**, lives in the
**system tray**, and can **launch at login** — so the always-on subsystems (MyHelper, the MCP
pool, the scheduler) keep running without a terminal + browser tab.

Status: **dev build, macOS first.** No installer / PyInstaller bundle yet (Phase 4, deferred).

## Architecture

```
┌─────────────────────────── Coworker.app (Tauri) ───────────────────────────┐
│  Rust shell (src-tauri/)                                                     │
│   • picks a free 127.0.0.1 port                                             │
│   • spawns  .venv/bin/coworker-server --host 127.0.0.1 --port <p>  (sidecar)│
│   • injects window.__COWORKER_HTTP__ / __COWORKER_WS__  before the SPA loads │
│   • system tray (Open · Settings · Quit); close-to-tray keeps the sidecar up │
│   • kills the sidecar on real Quit (no orphans)                             │
│                                                                             │
│  WebView → the built SPA (../dist) → talks to the sidecar over HTTP/WS       │
└─────────────────────────────────────────────────────────────────────────────┘
```

The **same SPA** still runs in the browser: `api.ts` reads the injected globals first, then
`VITE_COWORKER_*`, then the `127.0.0.1:8765` default. So `npm run dev` (browser) is unchanged.

Files: `surfaces/gui/src-tauri/{Cargo.toml, tauri.conf.json, build.rs, capabilities/default.json,
src/main.rs, src/lib.rs, icons/}`. Touch points in the SPA: `src/api.ts` (endpoint resolution),
`src/tauri.ts` (the `window.__TAURI__` bridge), `src/components/FolderGate.tsx` (native picker),
`src/components/ManageModal.tsx` (Settings → model API key), `src/App.tsx` (boot splash + tray
"Settings" event), `vite.config.ts` (`base: "./"`).

## Prerequisites (one-time)

Node 20 and the Xcode Command Line Tools are already present. You still need **Rust** and the
**Tauri CLI**:

```sh
# 1. Rust toolchain (network, ~5-10 min; writes ~/.cargo + ~/.rustup, edits your shell profile)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
cargo --version          # sanity check

# 2. Tauri CLI + plugins, as gui devDependencies
cd platform/surfaces/gui
npm i -D @tauri-apps/cli@^2
npm run tauri --version  # sanity check
```

The Rust **crates** (Tauri itself, dialog/autostart plugins) download on the first
`tauri dev`/`build` — the first compile takes a few minutes; later builds are incremental.

> Icons: `src-tauri/icons/` ships placeholder PNGs so `tauri dev` runs. Before a real
> `tauri build`, regenerate the full set from a source image: `npm run tauri icon ../assets/icon.png`.

## Run (dev)

```sh
cd platform/surfaces/gui
# Make the model key available one of two ways:
#   (a) export OPENAI_API_KEY in this shell — the sidecar inherits it, OR
#   (b) leave it unset and enter the key in the app: Manage → Settings (stored 0600 in
#       ~/.config/coworker/secrets.json, never sent to the model).
npm run tauri dev
```

`npm run tauri dev` runs `beforeDevCommand` (`npm run dev` → Vite on :1420), compiles the Rust
shell, opens the native window, and starts the sidecar on a random free port.

Verify:
- `lsof -iTCP -sTCP:LISTEN -nP | grep coworker-server` shows the sidecar on its port.
- Close the window → the app stays in the tray and `GET /v1/health` on that port still answers.
- Tray → **Quit** → the `coworker-server` process is gone (no orphan).

## How model access works under the desktop app

A Finder-launched `.app` does **not** inherit your shell environment, so `OPENAI_API_KEY` is
absent. The server therefore resolves the key as: env `OPENAI_API_KEY` → else the SecretStore
`provider:openai` profile (set via **Settings**). See `coworker/providers/openai_provider.py`
(`resolve_api_key`) and `GET/POST /v1/settings*`. A dev run launched from a shell with the env
var set works without re-entering the key (the sidecar inherits it).

## Onboarding wizard (first run)

On first launch the desktop app shows a 4-step setup wizard (`src/components/Onboarding.tsx`):
**Welcome → Workspace** (MyHelper's folder, native Browse) **→ Model & key** (default model +
OpenAI key) **→ Always-on** (Open-at-login, Keep-awake toggles + a "Show this on next startup"
checkbox). Each field saves as you go. Completion is recorded server-side (`prefs.json`
`onboarded`) so it isn't shown again; **Manage → Settings → "Run setup again"** re-opens it.
Backed by `GET /v1/settings` (+ `onboarded`, `models`) and `POST /v1/settings/{default-model,onboarded}`.

## Always-on UX

- **Tray:** Open · Settings · Quit. Closing the window **hides** it (sidecar keeps running);
  only **Quit** stops the sidecar.
- **Overlay title bar:** macOS `titleBarStyle: Overlay` + `hiddenTitle` — the traffic lights
  float over an edge-to-edge UI (no opaque OS bar). A 28px drag strip (`data-tauri-drag-region`)
  at the top moves the window; the SPA gets `tauri-overlay` top padding so nothing hides behind
  the lights.
- **Autostart:** `tauri-plugin-autostart` (LaunchAgent) behind the `get_autostart`/`set_autostart`
  commands; an **"Open at login"** toggle in Settings + the wizard.
- **Keep-awake:** the `set_keep_awake` command runs macOS `caffeinate -i -s` as a managed child so
  scheduled tasks fire while the Mac is idle. Persisted to `~/.config/coworker/desktop.json` and
  restored at launch; the `caffeinate` child is killed on Quit (like the sidecar).
- **Native folder picker:** under Tauri, `FolderGate` and the wizard show a **Browse…** button
  backed by the native macOS dialog (`pick_folder` Rust command); the browser keeps the
  typed-path gate.

## Phase 4 — distributable (.dmg) — BUILT

One command builds the standalone app + a drag-to-install `.dmg`:

```sh
platform/packaging/build_dmg.sh
# → src-tauri/target/release/bundle/dmg/Coworker_0.1.0_aarch64.dmg
```

What it does (see the script): PyInstaller-bundles `coworker-server` into a ~40 MB one-file
binary (`packaging/coworker-server.spec`, entry `packaging/server_entry.py`), drops it into
Tauri's `externalBin` slot, runs `tauri build --bundles app`, then wraps the `.app` in a `.dmg`
with `hdiutil`. The bundled server lands in `Coworker.app/Contents/MacOS/coworker-server`;
`lib.rs` `server_bin()` finds it next to the app executable (falling back to the venv in dev).

Spec wrinkles handled: aisuite isn't pip-installed (it's on `sys.path` via a `.pth` pointing at
the repo root) → `pathex` + `collect_submodules(coworker, aisuite)`; `uvicorn`/`certifi`/`anyio`
via `collect_all` (dynamic imports + the CA bundle for TLS); `mcp`, `ddgs`, `croniter` collected;
`slack_bolt`/`telegram` collected if present. Build deps added to the venv: `pyinstaller`, `typer`
(the latter just so `mcp`'s CLI submodule imports cleanly during collection).

The server self-resolves the model key from the SecretStore (no shell env in a Finder-launched
app), so the packaged app works once a key is entered in Settings/onboarding.

> **Unsigned.** First launch needs right-click → **Open** (Gatekeeper). Real code-signing +
> notarization (an Apple Developer ID) is a later step. Why `hdiutil` and not Tauri's own DMG:
> Tauri's `bundle_dmg.sh` drives Finder via AppleScript and fails in non-interactive shells;
> `hdiutil` is reliable and headless (no custom background, just app + Applications shortcut).
```

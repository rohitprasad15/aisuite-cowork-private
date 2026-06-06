# Quickstart: Open Coworker

Run these commands from the repo root.

## Prerequisites

- Python 3.10+
- Node.js 18+
- An OpenAI API key for model-backed chats
- For the native Mac app only: Rust / Cargo

## 1. Set up the Python backend

```bash
python3 -m venv platform/.venv
platform/.venv/bin/python -m pip install --upgrade pip
platform/.venv/bin/python -m pip install -e ./platform
```

## 2. Set up the GUI dependencies

```bash
cd platform/surfaces/gui
npm install
cd ../../..
```

## 3. Browser GUI: start the backend

Open a terminal at the repo root:

```bash
export OPENAI_API_KEY="sk-..."
PYTHONPATH="$PWD" platform/.venv/bin/coworker-server --port 8765
```

The `PYTHONPATH="$PWD"` part makes the backend use the local `aisuite` code from this repo.

To verify the backend is up:

```bash
curl http://127.0.0.1:8765/v1/health
```

You should see JSON with `"status":"ok"`.

## 4. Browser GUI: start the frontend

Open a second terminal at the repo root:

```bash
cd platform/surfaces/gui
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173/
```

The GUI talks to the backend at `http://127.0.0.1:8765` by default.

## Optional: Native Mac App

The native app is a Tauri shell around the same GUI. It starts its own backend sidecar on a random free port.

First, create the local sidecar shim that Tauri expects during development:

```bash
mkdir -p platform/surfaces/gui/src-tauri/binaries
TAURI_TRIPLE="$(rustc -vV | awk '/host:/ {print $2}')"
cat > "platform/surfaces/gui/src-tauri/binaries/coworker-server-$TAURI_TRIPLE" <<EOF
#!/usr/bin/env sh
set -eu
exec "$PWD/platform/.venv/bin/coworker-server" "\$@"
EOF
chmod +x "platform/surfaces/gui/src-tauri/binaries/coworker-server-$TAURI_TRIPLE"
```

Then launch the app:

```bash
cd platform/surfaces/gui
export OPENAI_API_KEY="sk-..."
npm run tauri dev
```

On first run, Rust will compile the Tauri app and download crates, so it can take a few minutes.

## If port 8765 is busy

Start the backend on another port:

```bash
export OPENAI_API_KEY="sk-..."
PYTHONPATH="$PWD" platform/.venv/bin/coworker-server --port 8766
```

Then start the GUI pointed at that backend:

```bash
cd platform/surfaces/gui
VITE_COWORKER_HTTP=http://127.0.0.1:8766 \
VITE_COWORKER_WS=ws://127.0.0.1:8766 \
npm run dev -- --host 127.0.0.1 --port 5173
```

## Notes

- Chat can be opened without choosing a workspace.
- Code and Cowork require choosing a local folder first.
- If you do not export `OPENAI_API_KEY`, open the GUI and add the key from Manage / Settings before sending model-backed prompts.

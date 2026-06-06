# Quickstart: Open Coworker in the Browser

This runs the Coworker backend plus the React browser GUI from a fresh clone.

## Prerequisites

- Python 3.10+
- Node.js 18+
- An OpenAI API key for model-backed chats

## 1. Clone the repo

```bash
git clone git@github.com:rohitprasad15/aisuite-cowork-private.git
cd aisuite-cowork-private
```

If you use HTTPS instead of SSH:

```bash
git clone https://github.com/rohitprasad15/aisuite-cowork-private.git
cd aisuite-cowork-private
```

## 2. Set up the Python backend

Run these from the repo root:

```bash
python3 -m venv platform/.venv
platform/.venv/bin/python -m pip install --upgrade pip
platform/.venv/bin/python -m pip install -e ./platform
```

## 3. Set up the browser GUI

```bash
cd platform/surfaces/gui
npm install
cd ../../..
```

## 4. Start the backend

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

## 5. Start the GUI

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

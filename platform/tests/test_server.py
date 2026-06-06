"""P6 gate tests — server: OpenAI-compatible endpoint, WS session API, REST."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient, ToolCall
from coworker.server import SessionManager, create_app


class ScriptedProvider(ProviderClient):
    """A ProviderClient that returns queued AssistantTurns (streams via base default)."""

    def __init__(self, turns):
        self._turns = list(turns)

    def complete(self, *, model, messages, tools=None, **settings):
        return self._turns.pop(0)

    def capabilities(self, model):
        return ModelCapabilities()


def _text(text):
    return AssistantTurn(text=text, finish_reason="stop")


def _tool(name, args, call_id="call_1"):
    return AssistantTurn(tool_calls=[ToolCall(id=call_id, name=name, arguments=args)])


def _client(tmp_path, turns):
    manager = SessionManager(workspace=tmp_path, provider=ScriptedProvider(turns))
    return TestClient(create_app(manager))


# -- REST -----------------------------------------------------------------------


def test_chat_completions_openai_shape(tmp_path):
    client = _client(tmp_path, [_text("hello world")])
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-5.5", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "hello world"
    assert body["choices"][0]["finish_reason"] == "stop"


def test_agents_and_memory_rest(tmp_path):
    client = _client(tmp_path, [])
    agents = client.get("/v1/agents").json()["agents"]
    assert {a["name"] for a in agents} >= {"code", "chat"}
    assert "skills" in client.get("/v1/skills").json()  # catalog (may be empty)

    added = client.post("/v1/memory", json={"content": "prefer pathlib"}).json()
    assert added["content"] == "prefer pathlib"
    assert any(m["content"] == "prefer pathlib" for m in client.get("/v1/memory").json()["memory"])


# -- WebSocket ------------------------------------------------------------------


def _drain(ws, on_permission=None):
    """Collect event types until turn_done; optionally answer permission_required."""
    types = []
    while True:
        event = ws.receive_json()
        types.append(event["type"])
        if event["type"] == "permission_required" and on_permission:
            ws.send_json({"type": "approval", "decision": on_permission})
        if event["type"] == "turn_done":
            return types


def test_ws_simple_turn(tmp_path):
    client = _client(tmp_path, [_text("done thinking")])
    with client.websocket_connect("/ws/session/s1") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "user_message", "text": "hello"})
        types = _drain(ws)
        assert "assistant_message" in types
        assert "turn_end" in types


def test_ws_approval_round_trip(tmp_path):
    client = _client(
        tmp_path,
        [_tool("write_file", {"path": "made.py", "content": "print(1)\n"}), _text("wrote it")],
    )
    with client.websocket_connect("/ws/session/s2") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "user_message", "text": "create made.py"})
        types = _drain(ws, on_permission="once")
        assert "permission_required" in types
        assert "tool_finished" in types
    assert (tmp_path / "made.py").read_text() == "print(1)\n"


def test_open_and_recent_workspaces(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    client = _client(tmp_path, [])
    opened = client.post("/v1/workspaces/open", json={"path": str(proj)}).json()
    assert opened["ok"] is True
    recents = client.get("/v1/workspaces/recent").json()["workspaces"]
    assert any(w["path"] == str(proj.resolve()) for w in recents)


def test_open_invalid_workspace(tmp_path):
    client = _client(tmp_path, [])
    bad = client.post("/v1/workspaces/open", json={"path": str(tmp_path / "nope")}).json()
    assert bad["ok"] is False


def test_open_workspace_create(tmp_path):
    client = _client(tmp_path, [])
    fresh = tmp_path / "fresh-project"
    assert not fresh.exists()
    res = client.post("/v1/workspaces/open", json={"path": str(fresh), "create": True}).json()
    assert res["ok"] is True
    assert fresh.is_dir()


def test_ws_requires_workspace_when_no_default(tmp_path):
    # Manager with no default workspace: a session with no folder is rejected.
    manager = SessionManager(workspace=None, data_dir=tmp_path, provider=ScriptedProvider([]))
    client = TestClient(create_app(manager))
    with client.websocket_connect("/ws/session/nofolder") as ws:
        first = ws.receive_json()
        assert first["type"] == "error"
        assert "workspace" in first["data"]["error"]


def test_ws_with_workspace_query(tmp_path):
    from urllib.parse import quote

    proj = tmp_path / "proj"
    proj.mkdir()
    manager = SessionManager(
        workspace=None, data_dir=tmp_path, provider=ScriptedProvider([_text("hi from proj")])
    )
    client = TestClient(create_app(manager))
    with client.websocket_connect(f"/ws/session/s?workspace={quote(str(proj))}") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["data"]["workspace"] == str(proj.resolve())
        ws.send_json({"type": "user_message", "text": "hello"})
        assert "turn_end" in _drain(ws)


def test_ws_chat_agent_needs_no_workspace(tmp_path):
    manager = SessionManager(
        workspace=None, data_dir=tmp_path, provider=ScriptedProvider([_text("hi from chat")])
    )
    client = TestClient(create_app(manager))
    with client.websocket_connect("/ws/session/chat1?agent=chat") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["data"]["agent"] == "chat"
        assert ready["data"]["workspace"] is None
        ws.send_json({"type": "user_message", "text": "hello"})
        assert "turn_end" in _drain(ws)


def test_ws_set_mode_auto_skips_approval(tmp_path):
    from urllib.parse import quote

    proj = tmp_path / "proj"
    proj.mkdir()
    manager = SessionManager(
        workspace=None,
        data_dir=tmp_path,
        provider=ScriptedProvider([_tool("write_file", {"path": "a.py", "content": "x"}), _text("done")]),
    )
    client = TestClient(create_app(manager))
    with client.websocket_connect(f"/ws/session/sm?workspace={quote(str(proj))}") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "set_mode", "mode": "auto"})
        ws.send_json({"type": "user_message", "text": "write a.py"})
        types = _drain(ws)  # no approval handler — would hang if it asked
        assert "permission_required" not in types
    assert (proj / "a.py").read_text() == "x"


def test_ws_session_resume_via_store(tmp_path):
    # First connection runs a turn and persists the session.
    client = _client(tmp_path, [_text("first answer")])
    with client.websocket_connect("/ws/session/keep") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "text": "remember this"})
        _drain(ws)
    # The session is now listed via REST.
    sessions = client.get("/v1/sessions").json()["sessions"]
    assert any(s["session_id"] == "keep" and s["messages"] > 0 for s in sessions)

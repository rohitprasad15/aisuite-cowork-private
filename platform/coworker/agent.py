"""Engine assembly from an Agent (Code / Chat / …).

Wires the agent's base tools + permissions + AGENTS.md (workspace agents) + memory +
the skill catalog (progressive disclosure) + load_skill into a TurnEngine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .agents import Agent, AgentContext, code_agent
from .automation import scheduling_tools
from .config import load_config
from .connectors import load_settings, make_send_message_tool
from .engine import Approver, TurnEngine
from .memory import MemoryStore, Scope, format_memories, memory_tools
from .permissions import Mode, PermissionEngine
from .project import load_agents_md
from .providers import OpenAIProvider, ProviderClient
from .secrets import SecretStore
from .skills import SkillLoader, skill_catalog_text, skill_tools
from .tools import ToolRegistry
from .web import make_web_fetch_tool, make_web_search_tool
from .tools.shell import LocalExecutor
from .tools.todo import TodoList


def _skill_dirs(workspace: Optional[Path]) -> list[Path]:
    dirs = [Path.home() / ".config" / "coworker" / "skills"]
    if workspace is not None:
        dirs.append(workspace / ".coworker" / "skills")
    return dirs


def build_engine(
    *,
    agent: Agent,
    workspace: Optional[str | Path] = None,
    model: str = "gpt-5.5",
    mode: Mode = Mode.INTERACTIVE,
    approver: Optional[Approver] = None,
    provider: Optional[ProviderClient] = None,
    allowed_commands: Optional[list[str]] = None,
    max_iterations: Optional[int] = None,
    model_settings: Optional[dict[str, Any]] = None,
    memory_store: Optional[MemoryStore] = None,
    messages: Optional[list[dict[str, Any]]] = None,
    extra_tools: Optional[list[Any]] = None,
    secrets: Optional[SecretStore] = None,
    task_store: Optional[Any] = None,
    session_id: Optional[str] = None,
) -> TurnEngine:
    ws = Path(workspace).expanduser().resolve() if workspace else None
    if agent.needs_workspace and ws is None:
        raise ValueError(f"agent '{agent.name}' requires a workspace")

    config = load_config(ws)
    executor = LocalExecutor(cwd=ws) if (agent.needs_workspace and ws is not None) else None
    todo = TodoList()
    context = AgentContext(workspace=ws, executor=executor, todo=todo)

    registry = ToolRegistry()
    registry.register_all(agent.build_tools(context))
    # MCP / connector tools (supplied by the manager) carry their own metadata + schema.
    if extra_tools:
        registry.register_all(extra_tools)
    # Outbound messaging: every agent gets `send_message` once a connector is configured.
    secrets = secrets or SecretStore()
    if any(s.enabled for s in load_settings(secrets).values()):
        registry.register(make_send_message_tool(secrets))
    # Web search + fetch: research tools for every agent (keyless DuckDuckGo default).
    registry.register(make_web_search_tool(secrets))
    registry.register(make_web_fetch_tool())
    # Scheduling: Cowork + MyHelper can set up scheduled tasks (origin = this session).
    if task_store is not None and ws is not None and agent.name in ("cowork", "myhelper"):
        origin = {"surface": agent.name, "session_id": session_id or "", "workspace": str(ws), "agent": agent.name}
        registry.register_all(scheduling_tools(task_store, origin=origin, default_workspace=str(ws)))

    instructions = agent.system_prompt
    if ws is not None:
        conventions = load_agents_md(ws)
        if conventions:
            instructions = f"{instructions}\n\n{conventions}"

    if memory_store is not None:
        registry.register_all(memory_tools(memory_store, workspace=str(ws) if ws else None))
        remembered = memory_store.list(scope=Scope.GLOBAL)
        if ws is not None:
            remembered += memory_store.list(scope=Scope.WORKSPACE, workspace=str(ws))
        block = format_memories(remembered)
        if block:
            instructions = f"{instructions}\n\n{block}"

    skill_loader = SkillLoader(_skill_dirs(ws))
    registry.register_all(skill_tools(skill_loader))
    catalog = skill_catalog_text(skill_loader)
    if catalog:
        instructions = f"{instructions}\n\n{catalog}"

    permissions = PermissionEngine(
        workspace_root=ws or Path.cwd(),
        mode=mode,
        allowed_commands=allowed_commands or config.allowed_commands,
        auto_allow_tools=set(config.auto_allow),
    )
    provider = provider or OpenAIProvider(default_model=model, secrets=secrets)

    engine = TurnEngine(
        provider=provider,
        registry=registry,
        permissions=permissions,
        model=model,
        instructions=instructions,
        approver=approver,
        max_iterations=max_iterations if max_iterations is not None else config.max_iterations,
        model_settings=model_settings,
        messages=messages,
    )
    engine.executor = executor  # type: ignore[attr-defined]
    engine.todo = todo  # type: ignore[attr-defined]
    engine.agent_name = agent.name  # type: ignore[attr-defined]
    engine.skill_loader = skill_loader  # type: ignore[attr-defined]
    return engine


def build_code_engine(**kwargs: Any) -> TurnEngine:
    """Back-compat shim: build the Code agent's engine."""
    return build_engine(agent=code_agent(), **kwargs)

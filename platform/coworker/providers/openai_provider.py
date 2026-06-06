"""OpenAI provider — the v1 model access implementation.

Uses the OpenAI Python SDK `chat.completions` API only (no Responses/Assistants), so
the later swap to aisuite (OpenAI-API-shaped) stays a near drop-in.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .base import AssistantTurn, ModelCapabilities, ProviderClient, StreamChunk, ToolCall
from .capabilities import capabilities_for


def resolve_api_key(secrets: Any = None) -> Optional[str]:
    """Resolve the OpenAI API key: env `OPENAI_API_KEY` first, else the SecretStore
    `provider:openai` profile (`{api_key}`). Lets a Tauri-launched sidecar — which does NOT
    inherit the shell env — still find a key the user entered in Settings. The value never
    enters the model context; it only configures the SDK client.
    """
    import os

    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    if secrets is not None:
        profile = secrets.get("provider:openai") or {}
        return profile.get("api_key") or None
    return None


class OpenAIProvider(ProviderClient):
    def __init__(
        self,
        client: Any = None,
        *,
        default_model: str = "gpt-5.5",
        api_key: Optional[str] = None,
        secrets: Any = None,
    ):
        # The SDK client is built lazily on first use, NOT at construction. This lets an engine
        # be assembled before any key exists — the desktop app lets you enter the key in Settings
        # *after* launch — and the super-agent engine to be built at startup with no key. The key
        # is resolved at call time: explicit `api_key` → env `OPENAI_API_KEY` → SecretStore. Tests
        # inject a `client` directly, bypassing all of this.
        self._client = client
        self._api_key = api_key
        self._secrets = secrets
        self.default_model = default_model

    def _ensure_client(self) -> Any:
        if self._client is None:
            # Lazy import so the SDK is only required when actually talking to OpenAI.
            from openai import OpenAI

            key = self._api_key or resolve_api_key(self._secrets)
            if not key:
                raise RuntimeError(
                    "No model API key configured. Set OPENAI_API_KEY in the environment, "
                    "or add your key in Manage → Settings."
                )
            self._client = OpenAI(api_key=key)
        return self._client

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **settings: Any,
    ) -> AssistantTurn:
        kwargs: dict[str, Any] = {"model": model, "messages": messages, **settings}
        if tools:
            kwargs["tools"] = tools

        response = self._ensure_client().chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        return AssistantTurn(
            text=getattr(message, "content", None),
            tool_calls=_parse_tool_calls(getattr(message, "tool_calls", None)),
            finish_reason=getattr(choice, "finish_reason", None),
            raw=response,
        )

    def capabilities(self, model: str) -> ModelCapabilities:
        return capabilities_for(model)

    def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **settings: Any,
    ):
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True, **settings}
        if tools:
            kwargs["tools"] = tools
        client = self._ensure_client()

        text_parts: list[str] = []
        tool_accum: dict[int, dict[str, str]] = {}
        finish_reason = None

        for chunk in client.chat.completions.create(**kwargs):
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            if delta is not None:
                content = getattr(delta, "content", None)
                if content:
                    text_parts.append(content)
                    yield StreamChunk(text_delta=content)
                for tc in getattr(delta, "tool_calls", None) or []:
                    acc = tool_accum.setdefault(
                        getattr(tc, "index", 0), {"id": "", "name": "", "args": ""}
                    )
                    if getattr(tc, "id", None):
                        acc["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            acc["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            acc["args"] += fn.arguments
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

        tool_calls = []
        for index in sorted(tool_accum):
            acc = tool_accum[index]
            try:
                arguments = json.loads(acc["args"]) if acc["args"] else {}
            except (TypeError, json.JSONDecodeError):
                arguments = {"_raw": acc["args"]}
            tool_calls.append(ToolCall(id=acc["id"], name=acc["name"], arguments=arguments))

        yield StreamChunk(
            turn=AssistantTurn(
                text="".join(text_parts) or None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        )


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for tc in raw_tool_calls or []:
        function = tc.function
        raw_args = getattr(function, "arguments", None)
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except (TypeError, json.JSONDecodeError):
            # Surface unparseable arguments rather than dropping the call; the engine
            # can return a tool-error so the model corrects itself.
            arguments = {"_raw": raw_args}
        calls.append(
            ToolCall(id=getattr(tc, "id", ""), name=function.name, arguments=arguments)
        )
    return calls

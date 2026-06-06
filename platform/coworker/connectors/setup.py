"""Connect / disconnect / list connectors — writes tokens to the SecretStore.

Pure functions over a SecretStore so they're testable without the server. `validate=False`
skips the network check (used by tests). Secrets are never returned — only status + the
public bot identity captured at connect time.
"""

from __future__ import annotations

from typing import Any

from ..secrets import SecretStore
from .descriptors import get_descriptor, list_descriptors


def connector_list(secrets: SecretStore) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in list_descriptors():
        profile = secrets.get(f"{d.name}:default") or {}
        connected = bool(profile.get("bot_token"))
        out.append(
            {
                "name": d.name,
                "title": d.title,
                "icon": d.icon,
                "blurb": d.blurb,
                "auth": d.auth,
                "two_way": d.two_way,
                "available": d.available,
                "fields": [f.to_dict() for f in d.fields],
                "instructions": d.instructions,
                "connected": connected,
                "account": profile.get("account"),
                "enabled": bool(profile.get("enabled", True)) and connected,
                "allowed_users": len(profile.get("allowed_users") or []),
            }
        )
    return out


def connect_connector(
    secrets: SecretStore, name: str, fields: dict[str, Any], *, validate: bool = True
) -> dict[str, Any]:
    d = get_descriptor(name)
    if d is None or not d.available:
        return {"ok": False, "error": "unknown or unavailable connector"}

    raw = {f.key: str(fields.get(f.key) or "").strip() for f in d.fields}
    missing = [f.label for f in d.fields if f.required and not raw.get(f.key)]
    if missing:
        return {"ok": False, "error": "missing: " + ", ".join(missing)}

    allowed = sorted({u.strip() for u in raw.get("allowed_users", "").split(",") if u.strip()})
    token_creds = {k: v for k, v in raw.items() if k != "allowed_users" and v}

    identity = None
    if validate and d.validate is not None:
        result = d.validate(token_creds)
        if not result.ok:
            return {"ok": False, "error": result.error or "validation failed"}
        identity = result.identity

    profile: dict[str, Any] = {"type": "token", "enabled": True, **token_creds}
    if any(f.key == "allowed_users" for f in d.fields):
        profile["allowed_users"] = allowed
    if identity:
        profile["account"] = identity
    secrets.put(f"{name}:default", profile)
    return {"ok": True, "account": identity}


def disconnect_connector(secrets: SecretStore, name: str) -> dict[str, Any]:
    return {"ok": secrets.delete(f"{name}:default")}

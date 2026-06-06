"""Connector descriptors — data that drives the guided setup wizard.

Adding a connector is (mostly) data, not UI code: a descriptor declares its auth method,
the fields the user pastes, step-by-step instructions, and a `validate` that confirms the
token by a real API call (and returns the bot identity to show back). Designed so a managed
one-click OAuth (`auth="oauth"`) can slot in later for the cloud product without changing the
data model — only the connect action differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Field:
    key: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""
    placeholder: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "secret": self.secret,
            "required": self.required,
            "help": self.help,
            "placeholder": self.placeholder,
        }


@dataclass
class ValidationResult:
    ok: bool
    identity: Optional[str] = None  # e.g. "@mybot" — shown back to the user, never a secret
    error: Optional[str] = None


@dataclass
class ConnectorDescriptor:
    name: str
    title: str
    icon: str
    blurb: str
    auth: str  # "bot_token" | "socket_app" | "oauth"
    two_way: bool
    fields: list[Field]
    instructions: list[str]
    available: bool = True  # False → shown as "soon"
    validate: Optional[Callable[[dict], ValidationResult]] = None


# -- validators (sync httpx, one-shot) -----------------------------------------
def _validate_telegram(creds: dict) -> ValidationResult:
    import httpx

    token = creds.get("bot_token", "")
    try:
        data = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
    except Exception as exc:
        return ValidationResult(False, error=str(exc))
    if data.get("ok"):
        return ValidationResult(True, identity="@" + str(data["result"].get("username", "bot")))
    return ValidationResult(False, error=data.get("description") or "invalid bot token")


def _validate_slack(creds: dict) -> ValidationResult:
    import httpx

    token = creds.get("bot_token", "")
    try:
        data = httpx.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        ).json()
    except Exception as exc:
        return ValidationResult(False, error=str(exc))
    if data.get("ok"):
        return ValidationResult(True, identity=f"{data.get('team', '?')} / {data.get('user', 'bot')}")
    return ValidationResult(False, error=data.get("error") or "invalid bot token")


_ALLOWED_FIELD = Field(
    key="allowed_users",
    label="Allowed user IDs",
    required=False,
    help="Comma-separated IDs allowed to message the bot. Leave empty, then DM the bot and use Capture.",
    placeholder="123456789",
)

DESCRIPTORS: list[ConnectorDescriptor] = [
    ConnectorDescriptor(
        name="telegram",
        title="Telegram",
        icon="✈",
        blurb="Two-way messaging with a Telegram bot.",
        auth="bot_token",
        two_way=True,
        fields=[
            Field("bot_token", "Bot token", secret=True, help="From @BotFather.", placeholder="123456:ABC-DEF…"),
            _ALLOWED_FIELD,
        ],
        instructions=[
            "Open Telegram and message @BotFather.",
            "Send /newbot and pick a name + username.",
            "Copy the HTTP API token it gives you and paste it below.",
            "After connecting, DM your new bot once, then use Capture to grab your user ID.",
        ],
        validate=_validate_telegram,
    ),
    ConnectorDescriptor(
        name="slack",
        title="Slack",
        icon="💬",
        blurb="Two-way messaging via a Slack app (Socket Mode).",
        auth="socket_app",
        two_way=True,
        fields=[
            Field("bot_token", "Bot token", secret=True, help="Bot User OAuth Token.", placeholder="xoxb-…"),
            Field("app_token", "App token", secret=True, help="App-level token for Socket Mode.", placeholder="xapp-…"),
            _ALLOWED_FIELD,
        ],
        instructions=[
            "Go to api.slack.com/apps → Create New App (from scratch).",
            "Settings → Socket Mode: enable it and generate an app-level token (xapp-) with connections:write.",
            "OAuth & Permissions: add bot scopes chat:write, app_mentions:read, im:history, channels:history.",
            "Install to workspace and copy the Bot User OAuth Token (xoxb-).",
            "Paste both tokens below and Connect, then invite the bot to a channel or DM it.",
        ],
        validate=_validate_slack,
    ),
    ConnectorDescriptor(
        name="gmail",
        title="Gmail",
        icon="✉",
        blurb="Draft, search, and send email (coming in C3).",
        auth="oauth",
        two_way=False,
        fields=[],
        instructions=[],
        available=False,
    ),
]

_BY_NAME = {d.name: d for d in DESCRIPTORS}


def list_descriptors() -> list[ConnectorDescriptor]:
    return list(DESCRIPTORS)


def get_descriptor(name: str) -> Optional[ConnectorDescriptor]:
    return _BY_NAME.get(name)

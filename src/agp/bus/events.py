"""
Message types flowing through the system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from pathlib import Path


@dataclass
class InboundMessage:
    """Message from a channel to the agent."""

    channel: str
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[Path] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        """Key for session storage: channel:chat_id"""
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message from the agent to a channel."""

    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[Path] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

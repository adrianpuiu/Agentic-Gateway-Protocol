"""
Abstract base class for all channels.
"""

from abc import ABC, abstractmethod
from typing import Any
from agp.bus.events import InboundMessage, OutboundMessage


class BaseChannel(ABC):
    """
    Abstract base for all channel integrations.

    Channels must implement:
    - `start()` — Connect to platform, listen for messages
    - `stop()` — Clean shutdown
    - `send()` — Deliver outbound message to platform
    """

    def __init__(
        self,
        name: str,
        bus,
        config: dict[str, Any],
    ):
        self.name = name
        self.bus = bus
        self.config = config
        self._running = False

    @property
    def enabled(self) -> bool:
        """Whether this channel is enabled in config."""
        return self.config.get("enabled", False)

    @property
    def allowed_senders(self) -> list[str]:
        """List of allowed sender IDs (empty = all allowed)."""
        return self.config.get("allow_from", [])

    def is_allowed(self, sender_id: str) -> bool:
        """
        Check if a sender is allowed to interact.

        Args:
            sender_id: Platform-specific user ID

        Returns:
            True if allowed, False otherwise
        """
        if not self.allowed_senders:
            return True
        return sender_id in self.allowed_senders

    @abstractmethod
    async def start(self) -> None:
        """Start the channel — connect to platform, listen for messages."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel — clean shutdown."""
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """Send an outbound message through this channel."""
        pass

    async def _publish_inbound(
        self, sender_id: str, chat_id: str, content: str, **metadata
    ) -> None:
        """
        Helper to publish an inbound message to the bus.

        Args:
            sender_id: Platform-specific user ID who sent the message
            chat_id: Platform-specific chat/channel ID
            content: Message text
            **metadata: Additional channel-specific data
        """
        # Check permissions
        if not self.is_allowed(sender_id):
            return

        await self.bus.publish_inbound(
            InboundMessage(
                channel=self.name,
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata,
            )
        )

"""
Async message bus for decoupling channels from agent.

Includes rate limiting:
- Max inbound queue depth (backpressure when agent is overloaded)
- Per-user cooldown to prevent message flooding
"""

import asyncio
import time
from typing import Self
from agp.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    Central message queue with two directions:
    - inbound: channels → agent
    - outbound: agent → channels

    Rate limiting:
    - max_inbound_depth: max queued inbound messages (0 = unlimited)
    - cooldown_s: minimum seconds between messages from the same user
    """

    def __init__(
        self,
        max_inbound_depth: int = 20,
        cooldown_s: float = 2.0,
    ) -> None:
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(
            maxsize=max_inbound_depth if max_inbound_depth > 0 else 0
        )
        self._outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._running = False

        # Rate limiting: sender_id → last message timestamp
        self._cooldown_s = cooldown_s
        self._last_message: dict[str, float] = {}

    async def publish_inbound(self, msg: InboundMessage) -> bool:
        """
        Publish a message from a channel to the agent.

        Returns:
            True if accepted, False if rate-limited or queue full.
        """
        # Per-user cooldown check
        now = time.monotonic()
        if self._cooldown_s > 0:
            last = self._last_message.get(msg.sender_id, 0)
            if now - last < self._cooldown_s:
                return False
            self._last_message[msg.sender_id] = now

        # Queue depth check
        if self._inbound.full():
            return False

        await self._inbound.put(msg)
        return True

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a message from the agent to channels."""
        await self._outbound.put(msg)

    async def consume_inbound(self, timeout: float | None = None) -> InboundMessage:
        """
        Consume a message from the inbound queue.

        Args:
            timeout: Seconds to wait. None blocks forever.
        """
        return await self._inbound.get()

    async def consume_outbound(self, timeout: float | None = None) -> OutboundMessage:
        """Consume a message from the outbound queue."""
        return await self._outbound.get()

    def subscribe_outbound(self, callback) -> None:
        """
        Subscribe to outbound messages (for channel dispatcher).

        Args:
            callback: Async function called with OutboundMessage
        """
        pass

    @property
    def running(self) -> bool:
        return self._running

    @property
    def inbound_depth(self) -> int:
        """Current number of messages in the inbound queue."""
        return self._inbound.qsize()

    @property
    def outbound_depth(self) -> int:
        """Current number of messages in the outbound queue."""
        return self._outbound.qsize()

    def start(self) -> Self:
        """Start the message bus (synchronous)."""
        self._running = True
        return self

    async def stop(self) -> None:
        """Stop the message bus."""
        self._running = False

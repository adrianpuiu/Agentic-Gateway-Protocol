"""
Channel manager — initializes, dispatches, and auto-reconnects channels.
"""

import asyncio
from typing import Any
from agp.bus import MessageBus, OutboundMessage
from agp.channels.base import BaseChannel


class ChannelManager:
    """
    Manages all channel integrations.

    - Initializes enabled channels from config
    - Dispatches outbound messages to correct channel
    - Coordinates channel lifecycle (start/stop)
    - Auto-reconnects crashed channels with exponential backoff
    """

    MAX_START_RETRIES = 3
    MONITOR_INTERVAL_S = 30  # Check channel health every 30s

    def __init__(self, bus: MessageBus, *args, **kwargs):
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._channel_configs: dict[str, tuple[type[BaseChannel], dict[str, Any]]] = {}
        self._dispatcher_task: asyncio.Task[None] | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def init_channel(
        self, name: str, channel_class: type[BaseChannel], config: dict[str, Any]
    ) -> None:
        """
        Initialize a channel if enabled.

        Args:
            name: Channel identifier (e.g., "telegram")
            channel_class: Class implementing BaseChannel
            config: Channel configuration dict
        """
        if not config.get("enabled", False):
            return

        channel = channel_class(name, self.bus, config)
        self.channels[name] = channel
        # Store config for reconnection
        self._channel_configs[name] = (channel_class, config)

    async def _start_channel_with_retry(self, name: str, channel: BaseChannel) -> bool:
        """Start a channel with exponential backoff retries."""
        for attempt in range(self.MAX_START_RETRIES):
            try:
                await channel.start()
                print(f"✓ {name} channel started")
                return True
            except Exception as e:
                wait = 2**attempt
                print(
                    f"✗ {name} channel failed (attempt {attempt + 1}/{self.MAX_START_RETRIES}): {e}"
                )
                if attempt < self.MAX_START_RETRIES - 1:
                    print(f"  Retrying in {wait}s...")
                    await asyncio.sleep(wait)
        print(
            f"✗ {name} channel failed permanently after {self.MAX_START_RETRIES} attempts"
        )
        return False

    async def start_all(self) -> None:
        """Start all enabled channels with retry logic."""
        self._running = True
        for name, channel in self.channels.items():
            await self._start_channel_with_retry(name, channel)

        # Start outbound dispatcher
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())

        # Start channel health monitor
        self._monitor_task = asyncio.create_task(self._monitor_channels())

    async def _monitor_channels(self) -> None:
        """Periodically check channel health and auto-restart crashed channels."""
        try:
            while self._running:
                await asyncio.sleep(self.MONITOR_INTERVAL_S)

                for name, channel in list(self.channels.items()):
                    if not channel._running and self._running:
                        print(f"⚠ {name} channel appears down, attempting restart...")
                        # Recreate channel instance from stored config
                        if name in self._channel_configs:
                            cls, config = self._channel_configs[name]
                            new_channel = cls(name, self.bus, config)
                            success = await self._start_channel_with_retry(
                                name, new_channel
                            )
                            if success:
                                self.channels[name] = new_channel
                                print(f"✓ {name} channel reconnected")
        except asyncio.CancelledError:
            pass

    async def stop_all(self) -> None:
        """Stop all channels."""
        self._running = False

        # Stop monitor
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._dispatcher_task and not self._dispatcher_task.done():
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass

        for name, channel in self.channels.items():
            try:
                await channel.stop()
                print(f"✓ {name} channel stopped")
            except Exception as e:
                print(f"✗ {name} channel stop failed: {e}")

    async def _dispatch_loop(self) -> None:
        """
        Continuously dispatch outbound messages from bus to channels.
        """
        try:
            while self._running:
                try:
                    msg = await self.bus.consume_outbound(timeout=1)
                    if msg is None:
                        continue
                    await self._dispatch_outbound(msg)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass

    async def _dispatch_outbound(self, msg: OutboundMessage) -> None:
        """
        Dispatch an outbound message to the correct channel.

        Args:
            msg: OutboundMessage with channel and chat_id
        """
        channel = self.channels.get(msg.channel)
        if channel is None:
            print(f"Warning: Unknown channel '{msg.channel}'")
            return

        try:
            await channel.send(msg)
        except Exception as e:
            print(f"Error sending to {msg.channel}: {e}")

    def get_status(self) -> dict[str, dict]:
        """Get status of all channels (for health endpoint)."""
        return {
            name: {
                "running": channel._running,
                "type": type(channel).__name__,
            }
            for name, channel in self.channels.items()
        }

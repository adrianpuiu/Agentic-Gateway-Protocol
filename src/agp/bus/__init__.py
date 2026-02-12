"""Message bus for decoupling channels from agent."""

from agp.bus.events import InboundMessage, OutboundMessage
from agp.bus.queue import MessageBus

__all__ = ["InboundMessage", "OutboundMessage", "MessageBus"]

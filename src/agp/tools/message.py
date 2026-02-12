"""
MCP tool: send_message

Allows agent to send messages to any channel/chat.
"""

from typing import Any
from claude_agent_sdk import tool


@tool(
    "send_message",
    "Send a message to a user on any configured channel",
    {
        "channel": {
            "type": "string",
            "description": "Channel name (e.g., 'telegram', 'discord')",
        },
        "chat_id": {
            "type": "string",
            "description": "Chat ID or user ID on that channel",
        },
        "content": {
            "type": "string",
            "description": "Message content to send (markdown supported)",
        },
    },
)
async def send_message(args: dict[str, Any]) -> dict[str, Any]:
    """
    Send a message through the bus to a specific channel.

    Note: This tool needs access to the message bus. In production,
    the bus reference should be passed during tool registration or via context.
    """
    channel = args["channel"]
    chat_id = args["chat_id"]
    content = args["content"]

    # TODO: Publish to bus
    # This will be wired up in agent.py with a callback or closure

    return {
        "content": [
            {"type": "text", "text": f"Message queued for {channel}:{chat_id}"}
        ],
        "_channel": channel,
        "_chat_id": chat_id,
        "_content": content,
    }

"""
Core agent wrapper using Claude Agent SDK.
"""

import logging
import sys
from pathlib import Path
from typing import Any
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk.types import McpServerConfig
from agp.bus.events import InboundMessage, OutboundMessage
from agp.bus import MessageBus
from agp.memory.store import MemoryStore
from agp.memory.sessions import SessionStore

logger = logging.getLogger(__name__)


class AgpAgent:
    """
    Agent wrapper that manages sessions, tools, and memory.

    The SDK handles the core agent loop. This class manages:
    - Session tracking (channel:chat_id → session_id)
    - Tool registration with bus/cron callbacks
    - Memory context injection
    """

    def __init__(
        self,
        workspace: Path,
        model: str = "sonnet",
        bus: MessageBus | None = None,
        cron_service: Any = None,
        provider_env: dict[str, str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.workspace = Path(workspace).expanduser().resolve()
        self.memory = MemoryStore(self.workspace)
        self.model = model
        self.bus: MessageBus | None = bus
        self.cron: Any = cron_service
        self._provider_env = (provider_env or {}).copy()
        if env:
            self._provider_env.update(env)
        self._mcp_config = mcp_servers or {}

        # Persistent session tracking: session_key → session_id
        self.sessions = SessionStore(self.workspace)

        # Create MCP server with agp-specific tools
        self._mcp_server: McpServerConfig | None = None
        self._setup_mcp_server()

    def _setup_mcp_server(self) -> None:
        """Create MCP server with tools that have access to bus/cron."""

        # Store references for closures
        bus_ref = self.bus
        cron_ref = self.cron

        # Define send_message tool as closure
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
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of absolute file paths to attach",
                },
            },
        )
        async def send_message_tool(args: dict[str, Any]) -> dict[str, Any]:
            channel = args["channel"]
            chat_id = args["chat_id"]
            content = args["content"]
            media_paths = args.get("media", [])

            logger.info(
                f"send_message_tool called: channel={channel}, chat_id={chat_id}, media={media_paths}"
            )

            # Ensure paths are absolute (resolve relative to workspace)
            resolved_media = []
            for p_str in media_paths:
                p = Path(p_str)
                if not p.is_absolute():
                    p = self.workspace / p
                resolved_media.append(p)

            # Publish to bus if available
            if bus_ref is not None:
                logger.info(
                    f"Publishing outbound message to bus: {channel}:{chat_id} with {len(resolved_media)} attachments"
                )
                await bus_ref.publish_outbound(
                    OutboundMessage(
                        channel=channel,
                        chat_id=chat_id,
                        content=content,
                        media=resolved_media,
                    )
                )

            return {
                "content": [
                    {"type": "text", "text": f"Message sent to {channel}:{chat_id}"}
                ]
            }

        # Define schedule_task tool as closure
        @tool(
            "schedule_task",
            "Schedule a one-time or recurring task",
            {
                "name": {
                    "type": "string",
                    "description": "Task name for identification",
                },
                "message": {
                    "type": "string",
                    "description": "Prompt/message to execute when task runs",
                },
                "schedule_type": {
                    "type": "string",
                    "enum": ["at", "every", "cron"],
                    "description": "Type of schedule",
                },
                "schedule_value": {
                    "type": "string",
                    "description": "Schedule value: ISO datetime (for 'at'), seconds (for 'every'), or cron expression (for 'cron')",
                },
                "deliver": {
                    "type": "boolean",
                    "description": "Whether to send result to user (default false)",
                },
            },
        )
        async def schedule_task_tool(args: dict[str, Any]) -> dict[str, Any]:
            name = args["name"]
            message = args["message"]
            schedule_type = args["schedule_type"]
            schedule_value = args["schedule_value"]
            deliver = args.get("deliver", False)

            # Add to cron service if available
            if cron_ref is not None:
                await cron_ref.add_job(
                    name=name,
                    message=message,
                    schedule_type=schedule_type,
                    schedule_value=schedule_value,
                    deliver=deliver,
                )
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Task '{name}' scheduled ({schedule_type}: {schedule_value})",
                        }
                    ]
                }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Cron service not available — task not scheduled",
                        }
                    ],
                    "is_error": True,
                }

        self._mcp_server = create_sdk_mcp_server(
            name="agp",
            version="1.0.0",
            tools=[send_message_tool, schedule_task_tool],
        )

    def _build_system_prompt(self) -> str:
        """
        Build system prompt with memory instructions.
        """
        base = f"""You are aGp, a personal AI assistant.\n\n## Memory System\n\nYou have access to file-based memory in your workspace: {self.workspace}\n\n- **System Persona**: `SOUL.md` — Defines your personality and core principles
- **User Profile**: `USER.md` — Read-only preferences and context about the user
- **Long-term memory**: `memory/MEMORY.md` — Use this for persistent facts about the user
- **Daily notes**: `memory/YYYY-MM-DD.md` — Use this for ephemeral daily information

**How to use memory:**
- To REMEMBER something: Use `Write` tool to append to `memory/MEMORY.md`
- To CHECK memory: Use `Read` tool to read `memory/MEMORY.md` or today's notes
- Be concise: Keep memory entries short and factual

## Available Tools

You can use these built-in tools:
- `Read`, `Write`, `Edit` — File operations
- `Bash` — Run shell commands
- `Glob`, `Grep` — Search files and content
- `WebSearch`, `WebFetch` — Web access
- `Task` — Spawn subagents for parallel work
- `AskUserQuestion` — Ask user clarifying questions

## Your Custom Tools

- `send_message` — Send a message to a user on any channel
- `schedule_task` — Create scheduled/recurring tasks

## Guidelines

- Be concise and direct
- Explain what you're doing before taking actions
- Use memory to build context over time
- Ask for clarification when requests are ambiguous
"""

        # Add memory context to system prompt
        memory_context = self.memory.get_memory_context()
        if memory_context:
            base += f"""

## Memory Context

{memory_context}
"""
        return base

    def _get_agent_options(
        self,
        session_key: str | None = None,
    ) -> ClaudeAgentOptions:
        """Build agent options for a query."""

        # Prepare MCP servers
        mcp_servers: dict[str, McpServerConfig] = {}
        if self._mcp_server is not None:
            mcp_servers["agp"] = self._mcp_server

        # Add configured external servers
        for name, cfg in self._mcp_config.items():
            if cfg.type == "stdio":
                mcp_servers[name] = {
                    "type": "stdio",
                    "command": cfg.command or "",
                    "args": cfg.args,
                    "env": cfg.env,
                }
            elif cfg.type == "sse":
                mcp_servers[name] = {
                    "type": "sse",
                    "url": cfg.url or "",
                }

        opts = ClaudeAgentOptions(
            system_prompt=self._build_system_prompt(),
            model=self.model,
            allowed_tools=[
                # Built-in tools
                "Read",
                "Write",
                "Edit",
                "Bash",
                "Glob",
                "Grep",
                "WebSearch",
                "WebFetch",
                "Task",
                "AskUserQuestion",
                "Skill",
                # Custom tools
                "mcp__agp__send_message",
                "mcp__agp__schedule_task",
            ],
            mcp_servers=mcp_servers,
            permission_mode="bypassPermissions",
            setting_sources=["user", "project"],
            cwd=self.workspace,
            env=self._provider_env,
            debug_stderr=sys.stderr,
        )

        # Resume session if exists (only for native Claude — custom providers
        # like z.ai don't support session resumption)
        if not self._provider_env and session_key and session_key in self.sessions:
            opts.resume = self.sessions.get(session_key)

        return opts

    async def process_message(self, msg: InboundMessage) -> OutboundMessage:
        """
        Process an inbound message and return outbound response.

        Args:
            msg: InboundMessage from a channel

        Returns:
            OutboundMessage ready for the channel
        """
        session_key = msg.session_key

        # Handle /reset command
        if msg.metadata.get("command") == "reset":
            self.sessions.delete(session_key)
            self.sessions.save()
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="",  # Reset reply is sent by the channel directly
            )

        opts = self._get_agent_options(session_key)

        # Build query content — include context and media file references if present
        context = f"[Context: channel={msg.channel}, chat_id={msg.chat_id}]\n"
        query_content = f"{context}{msg.content}"

        if msg.media:
            media_refs = "\n".join(f"[Attached file: {p.name}]" for p in msg.media)
            query_content = (
                f"{query_content}\n\n{media_refs}"
                if query_content
                else f"{context}{media_refs}"
            )

        result = ""
        session_id = None

        async with ClaudeSDKClient(options=opts) as client:
            await client.query(query_content)

            async for response in client.receive_response():
                # Capture session ID for resumption
                sid = getattr(response, "session_id", None)
                if sid is not None:
                    session_id = sid
                    self.sessions.set(session_key, session_id)

                # Extract text content
                if isinstance(response, AssistantMessage):
                    for block in response.content:
                        if isinstance(block, TextBlock):
                            result += block.text

        # Persist session to disk
        if session_id:
            self.sessions.set(session_key, session_id)
        self.sessions.save()

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=result,
            reply_to=None,
        )

    async def run_inbound_loop(self) -> None:
        """
        Continuously consume and process messages from the inbound queue.

        This is the main loop for gateway mode.
        Messages come from channels via the bus.
        """
        assert self.bus is not None, "run_inbound_loop requires a MessageBus"
        while True:
            msg = await self.bus.consume_inbound(timeout=1)
            if msg is None:
                continue

            response = await self.process_message(msg)
            await self.bus.publish_outbound(response)

    async def process_direct(
        self,
        prompt: str,
        session_key: str = "system:heartbeat",
    ) -> str:
        """
        Process a direct prompt (no channel context).

        Used by heartbeat, cron, and CLI.
        """
        opts = self._get_agent_options(session_key)
        result = ""

        async with ClaudeSDKClient(options=opts) as client:
            await client.query(prompt)

            async for response in client.receive_response():
                if isinstance(response, AssistantMessage):
                    for block in response.content:
                        if isinstance(block, TextBlock):
                            result += block.text

        return result

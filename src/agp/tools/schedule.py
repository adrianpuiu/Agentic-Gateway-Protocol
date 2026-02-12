"""
MCP tool: schedule_task

Allows agent to create scheduled/cron tasks.
"""

from typing import Any
from claude_agent_sdk import tool


@tool(
    "schedule_task",
    "Schedule a one-time or recurring task",
    {
        "name": {"type": "string", "description": "Task name for identification"},
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
async def schedule_task(args: dict[str, Any]) -> dict[str, Any]:
    """
    Schedule a task via the cron service.

    Note: This tool needs access to the cron service. In production,
    the cron service reference should be passed during tool registration.
    """
    name = args["name"]
    message = args["message"]
    schedule_type = args["schedule_type"]
    schedule_value = args["schedule_value"]
    deliver = args.get("deliver", False)

    # TODO: Add to cron service
    # This will be wired up in agent.py with a callback or closure

    return {
        "content": [
            {
                "type": "text",
                "text": f"Task '{name}' scheduled ({schedule_type}: {schedule_value})",
            }
        ],
        "_name": name,
        "_message": message,
        "_schedule_type": schedule_type,
        "_schedule_value": schedule_value,
        "_deliver": deliver,
    }

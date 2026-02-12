"""
Cron data types.
"""

from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime


ScheduleType = Literal["at", "every", "cron"]


@dataclass
class CronJob:
    """
    A scheduled task.

    Attributes:
        name: Unique identifier for this job
        message: Prompt/message to execute when job runs
        schedule_type: Type of schedule ("at", "every", "cron")
        schedule_value: ISO datetime (at), seconds (every), or cron expr (cron)
        deliver: Whether to send result to user
        enabled: Whether job is active
        next_run_at: When this job should next run
    """

    name: str
    message: str
    schedule_type: ScheduleType
    schedule_value: str
    deliver: bool = False
    enabled: bool = True
    next_run_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class CronExecutionResult:
    """Result of a cron job execution."""

    job_name: str
    success: bool
    result: str | None = None
    error: str | None = None
    executed_at: datetime = field(default_factory=datetime.now)

"""
Cron service for scheduled tasks.

Simplifed implementation without persistence (TODO: add JSON storage).
"""

import asyncio
from datetime import datetime, timedelta

from croniter import croniter

from agp.cron.types import CronJob, ScheduleType, CronExecutionResult


class CronService:
    """
    Scheduled tasks service.

    Three schedule types:
    - "at": One-time execution at specific ISO datetime
    - "every": Interval-based (every N seconds)
    - "cron": Cron expression (with timezone awareness)
    """

    def __init__(
        self,
        agent,  # AgpAgent reference for executing jobs
        interval_s: int = 60,
    ):
        """
        Initialize cron service.

        Args:
            agent: AgpAgent instance for executing jobs
            interval_s: How often to check for due jobs (default 60s)
        """
        self.agent = agent
        self.interval_s = interval_s
        self.jobs: dict[str, CronJob] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def _compute_next_run(self, job: CronJob) -> datetime | None:
        """
        Compute next run time for a job.

        Args:
            job: CronJob with schedule_type and schedule_value

        Returns:
            Next run datetime, or None if job is expired (for "at" type)
        """
        now = datetime.now()

        if job.schedule_type == "at":
            # One-time: parse ISO datetime
            try:
                run_at = datetime.fromisoformat(job.schedule_value)
                return run_at if run_at > now else None
            except ValueError:
                return None

        elif job.schedule_type == "every":
            # Interval: add seconds to now
            try:
                seconds = int(job.schedule_value)
                return now + timedelta(seconds=seconds)
            except ValueError:
                return None

        elif job.schedule_type == "cron":
            # Cron expression
            try:
                iter = croniter(job.schedule_value, now)
                return iter.get_next(datetime)
            except Exception:
                return None

        return None

    async def add_job(
        self,
        name: str,
        message: str,
        schedule_type: ScheduleType,
        schedule_value: str,
        deliver: bool = False,
    ) -> CronJob:
        """
        Add a new scheduled job.

        Args:
            name: Unique job identifier
            message: Prompt/message to execute when job runs
            schedule_type: "at", "every", or "cron"
            schedule_value: ISO datetime, seconds, or cron expression
            deliver: Whether to deliver result to user

        Returns:
            Created CronJob
        """
        job = CronJob(
            name=name,
            message=message,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            deliver=deliver,
        )
        job.next_run_at = self._compute_next_run(job)
        self.jobs[name] = job
        return job

    async def remove_job(self, name: str) -> bool:
        """
        Remove a job.

        Args:
            name: Job identifier

        Returns:
            True if removed, False if not found
        """
        if name in self.jobs:
            del self.jobs[name]
            return True
        return False

    async def _execute_job(self, job: CronJob) -> CronExecutionResult:
        """
        Execute a job via agent.

        Args:
            job: CronJob to execute

        Returns:
            Execution result
        """
        if self.agent is None:
            return CronExecutionResult(
                job_name=job.name,
                success=False,
                error="No agent configured",
            )

        try:
            # Execute job via agent
            result = await self.agent.process_direct(
                prompt=job.message,
                session_key=f"cron:job:{job.name}",
            )

            # If deliver=True, the agent should use send_message tool
            # The result will be handled by the agent's tool system

            return CronExecutionResult(
                job_name=job.name,
                success=True,
                result=result,
            )
        except Exception as e:
            return CronExecutionResult(
                job_name=job.name,
                success=False,
                error=str(e),
            )

    async def _tick(self) -> None:
        """Check for due jobs and execute them."""
        now = datetime.now()

        for name, job in list(self.jobs.items()):
            if not job.enabled:
                continue

            if job.next_run_at and job.next_run_at <= now:
                # Execute job
                await self._execute_job(job)

                # Handle "at" jobs (one-time, disable after running)
                if job.schedule_type == "at":
                    job.enabled = False

                # Recompute next run
                job.next_run_at = self._compute_next_run(job)

    async def _run_loop(self) -> None:
        """Main cron loop."""
        while self._running:
            await self._tick()
            await asyncio.sleep(self.interval_s)

    async def start(self) -> None:
        """Start the cron service."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        if self._task:
            self._task.cancel()

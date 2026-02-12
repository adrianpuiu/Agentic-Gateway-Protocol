"""
Heartbeat service — periodic wake-up for proactive tasks.

Checks HEARTBEAT.md and prompts agent to follow instructions.
"""

import asyncio
from pathlib import Path


DEFAULT_HEARTBEAT_INTERVAL_S = 30 * 60  # 30 minutes


class HeartbeatService:
    """
    Periodic wake-up service.

    Every interval:
    1. Reads HEARTBEAT.md from workspace
    2. If content exists, calls agent to process it
    3. Agent processes HEARTBEAT.md instructions
    4. If agent responds "HEARTBEAT_OK", nothing needed
    """

    def __init__(
        self,
        agent,  # AgpAgent reference
        interval_s: int = DEFAULT_HEARTBEAT_INTERVAL_S,
    ):
        """
        Initialize heartbeat service.

        Args:
            agent: AgpAgent instance for processing tasks
            interval_s: Seconds between checks (default 30 min)
        """
        self.agent = agent
        self.workspace = (
            Path(agent.workspace)
            if isinstance(agent.workspace, Path)
            else Path(agent.workspace)
        )
        self.heartbeat_path = self.workspace / "HEARTBEAT.md"
        self.interval_s = interval_s
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def _is_heartbeat_empty(self, content: str) -> bool:
        """
        Check if HEARTBEAT.md has actionable content.

        Skips:
        - Empty lines
        - Lines starting with #
        - HTML comments <!-- ... -->
        - Lines that are just checkboxes with no text
        """
        if not content or not content.strip():
            return True

        for line in content.strip().split("\n"):
            stripped = line.strip()

            # Skip empty, comments, HTML comments
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("<!--"):
                continue

            # If we got here, there's actionable content
            return False

        return True

    async def _tick(self) -> None:
        """Check HEARTBEAT.md and trigger if needed."""
        if not self.heartbeat_path.exists():
            return

        content = self.heartbeat_path.read_text(encoding="utf-8")

        # Skip if empty or only comments
        if self._is_heartbeat_empty(content):
            return

        # Trigger heartbeat via agent
        if self.agent is not None:
            prompt = """Check HEARTBEAT.md in your workspace and complete any tasks listed there.

For each unchecked task:
- Read the task description
- Use your tools to complete the task
- Mark it as done by editing HEARTBEAT.md to remove the task or check it off

If all tasks are complete or there are no tasks, reply with just: HEARTBEAT_OK"""

            try:
                response = await self.agent.process_direct(
                    prompt=prompt,
                    session_key="system:heartbeat",
                )

                # Check if agent said nothing to do
                if response and "HEARTBEAT_OK" in response:
                    pass  # Nothing needed
            except Exception as e:
                print(f"Heartbeat error: {e}")

    async def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            await asyncio.sleep(self.interval_s)
            if self._running:  # Check again in case stopped during sleep
                await self._tick()

    async def start(self) -> None:
        """Start the heartbeat service."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        if self._task:
            self._task.cancel()

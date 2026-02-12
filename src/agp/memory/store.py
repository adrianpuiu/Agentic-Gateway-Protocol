"""
File-based memory store.

Agent uses built-in Read/Write tools to interact with these files.
This class provides helpers for context building.
"""

from pathlib import Path
from datetime import datetime


class MemoryStore:
    """
    File-based memory with two tiers:

    1. Long-term: {workspace}/memory/MEMORY.md — persistent facts
    2. Daily: {workspace}/memory/YYYY-MM-DD.md — ephemeral notes
    """

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.memory_dir = self.workspace / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.long_term_path = self.memory_dir / "MEMORY.md"
        self.user_profile_path = self.workspace / "USER.md"

    def get_user_profile(self) -> str:
        """Read user profile file. Returns empty string if not exists."""
        if self.user_profile_path.exists():
            return self.user_profile_path.read_text(encoding="utf-8")
        return ""

    def get_soul(self) -> str:
        """Read soul file. Returns empty string if not exists."""
        soul_path = self.workspace / "SOUL.md"
        if soul_path.exists():
            return soul_path.read_text(encoding="utf-8")
        return ""

    def get_long_term(self) -> str:
        """Read long-term memory file. Returns empty string if not exists."""
        if self.long_term_path.exists():
            return self.long_term_path.read_text(encoding="utf-8")
        return ""

    def get_today(self) -> str:
        """Read today's daily notes. Returns empty string if not exists."""
        today_path = self._get_today_path()
        if today_path.exists():
            return today_path.read_text(encoding="utf-8")
        return ""

    def _get_today_path(self) -> Path:
        """Get path for today's notes."""
        return self.memory_dir / datetime.now().strftime("%Y-%m-%d.md")

    def get_memory_context(self) -> str:
        """
        Build memory context for system prompt.

        Returns formatted string with both long-term and today's notes.
        """
        parts = []

        soul = self.get_soul()
        if soul.strip():
            parts.append(f"## System Persona (SOUL)\n\n{soul}")

        user_profile = self.get_user_profile()
        if user_profile.strip():
            parts.append(f"## User Profile (Do not edit)\n\n{user_profile}")

        long_term = self.get_long_term()
        if long_term.strip():
            parts.append(f"## Long-term Memory\n\n{long_term}")

        today = self.get_today()
        if today.strip():
            parts.append(
                f"## Today's Notes ({datetime.now().strftime('%Y-%m-%d')})\n\n{today}"
            )

        if not parts:
            return ""

        return "\n\n---\n\n".join(parts)

    def list_recent_files(self, days: int = 7) -> list[tuple[str, Path]]:
        """
        List recent memory files.

        Returns:
            List of (date_string, path) tuples sorted newest first.
        """
        files = []
        for f in self.memory_dir.glob("????-??-??.md"):
            # Skip long-term memory
            if f.name == "MEMORY.md":
                continue
            date_str = f.stem  # YYYY-MM-DD
            files.append((date_str, f))

        # Sort by date descending (newest first)
        files.sort(key=lambda x: x[0], reverse=True)
        return files[:days]

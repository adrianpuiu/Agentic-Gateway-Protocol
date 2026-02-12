"""
Persistent session storage — JSON file on disk.
"""

import json
from pathlib import Path


class SessionStore:
    """
    Persist agent sessions (session_key → session_id) to a JSON file.

    Sessions survive restarts so users don't lose conversation context.
    """

    def __init__(self, workspace: Path):
        self._path = Path(workspace) / "sessions.json"
        self._sessions: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Load sessions from disk."""
        if self._path.exists():
            try:
                self._sessions = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Could not load sessions: {e}")
                self._sessions = {}

    def save(self) -> None:
        """Write sessions to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._sessions, indent=2))
        except OSError as e:
            print(f"Warning: Could not save sessions: {e}")

    def get(self, key: str) -> str | None:
        """Get session ID for a key."""
        return self._sessions.get(key)

    def set(self, key: str, value: str) -> None:
        """Set session ID for a key."""
        self._sessions[key] = value

    def delete(self, key: str) -> None:
        """Delete a session."""
        self._sessions.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return key in self._sessions

    def __getitem__(self, key: str) -> str:
        return self._sessions[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._sessions[key] = value

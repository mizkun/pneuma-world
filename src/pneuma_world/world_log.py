"""WorldLog: records world events to daily markdown files."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

# JST (Asia/Tokyo, UTC+9)
JST = timezone(timedelta(hours=9))


class WorldLog:
    """Records world events to ``vault/world/YYYY-MM-DD.md``.

    Events are grouped by time with ``## HH:MM`` headers.
    A new header is only added when the time changes.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or Path("vault/world")
        self._last_time_header: dict[str, str] = {}  # filename -> last HH:MM

    def record_action(
        self, character_name: str, action: str, world_time: datetime
    ) -> None:
        """Record a character action.

        Format: ``[キャラA] 部室に来た``
        """
        entry = f"[{character_name}] {action}"
        self._write_entry(entry, world_time)

    def record_speech(
        self, character_name: str, speech: str, world_time: datetime
    ) -> None:
        """Record character speech.

        Format: ``[キャラA] 「おはよう」``
        """
        entry = f"[{character_name}] 「{speech}」"
        self._write_entry(entry, world_time)

    def record_thought(
        self, character_name: str, thought: str, world_time: datetime
    ) -> None:
        """Record internal thought.

        Format: ``[キャラA] (このコード動かない……)``
        """
        entry = f"[{character_name}] ({thought})"
        self._write_entry(entry, world_time)

    def _write_entry(self, entry: str, world_time: datetime) -> None:
        """Write an entry to the appropriate daily log file."""
        # Ensure log directory exists
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # Convert to JST for display
        jst_time = world_time.astimezone(JST)
        date_str = jst_time.strftime("%Y-%m-%d")
        time_str = jst_time.strftime("%H:%M")
        filename = f"{date_str}.md"
        filepath = self._log_dir / filename

        lines: list[str] = []

        # Add time header if it changed
        last_header = self._last_time_header.get(filename)
        if last_header != time_str:
            lines.append(f"\n## {time_str}\n")
            self._last_time_header[filename] = time_str

        lines.append(f"{entry}\n")

        with open(filepath, "a", encoding="utf-8") as f:
            f.writelines(lines)

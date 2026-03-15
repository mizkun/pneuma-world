"""Tests for WorldLog."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from pneuma_world.world_log import WorldLog

# JST timezone for tests
JST = timezone(timedelta(hours=9))


class TestWorldLog:
    """Tests for WorldLog file output."""

    def test_record_action(self, tmp_path: Path) -> None:
        log = WorldLog(log_dir=tmp_path)
        world_time = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)

        log.record_action("アイネ", "部室に来た", world_time)

        log_file = tmp_path / "2026-03-01.md"
        assert log_file.exists()
        content = log_file.read_text()
        assert "## 10:30" in content
        assert "[アイネ] 部室に来た" in content

    def test_record_speech(self, tmp_path: Path) -> None:
        log = WorldLog(log_dir=tmp_path)
        world_time = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)

        log.record_speech("アイネ", "おはよう", world_time)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        assert "[アイネ] 「おはよう」" in content

    def test_record_thought(self, tmp_path: Path) -> None:
        log = WorldLog(log_dir=tmp_path)
        world_time = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)

        log.record_thought("アイネ", "このコード動かない……", world_time)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        assert "[アイネ] (このコード動かない……)" in content

    def test_time_header_changes(self, tmp_path: Path) -> None:
        """New time header is added when the time changes."""
        log = WorldLog(log_dir=tmp_path)
        time1 = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)
        time2 = datetime(2026, 3, 1, 11, 0, 0, tzinfo=JST)

        log.record_action("アイネ", "部室に来た", time1)
        log.record_action("クロエ", "廊下を歩いている", time2)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        assert "## 10:30" in content
        assert "## 11:00" in content

    def test_same_time_no_duplicate_header(self, tmp_path: Path) -> None:
        """Same time should not add a duplicate header."""
        log = WorldLog(log_dir=tmp_path)
        world_time = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)

        log.record_action("アイネ", "部室に来た", world_time)
        log.record_speech("アイネ", "おはよう", world_time)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        # Only one "## 10:30" header
        assert content.count("## 10:30") == 1

    def test_different_dates_different_files(self, tmp_path: Path) -> None:
        """Different dates should write to different files."""
        log = WorldLog(log_dir=tmp_path)
        time1 = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)
        time2 = datetime(2026, 3, 2, 9, 0, 0, tzinfo=JST)

        log.record_action("アイネ", "部室に来た", time1)
        log.record_action("アイネ", "家を出た", time2)

        assert (tmp_path / "2026-03-01.md").exists()
        assert (tmp_path / "2026-03-02.md").exists()

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        """Records should append to an existing file."""
        log = WorldLog(log_dir=tmp_path)
        world_time = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)

        log.record_action("アイネ", "部室に来た", world_time)
        log.record_speech("アイネ", "おはよう", world_time)
        log.record_thought("アイネ", "今日もがんばろう", world_time)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        lines = [line for line in content.strip().split("\n") if line.strip()]
        # Header + 3 records
        assert len(lines) == 4

    def test_creates_log_dir_if_not_exists(self, tmp_path: Path) -> None:
        """Log directory should be created if it doesn't exist."""
        log_dir = tmp_path / "sub" / "dir"
        log = WorldLog(log_dir=log_dir)
        world_time = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)

        log.record_action("アイネ", "部室に来た", world_time)

        assert (log_dir / "2026-03-01.md").exists()

    def test_order_of_entries(self, tmp_path: Path) -> None:
        """Entries should appear in chronological order."""
        log = WorldLog(log_dir=tmp_path)
        t1 = datetime(2026, 3, 1, 10, 0, 0, tzinfo=JST)
        t2 = datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST)
        t3 = datetime(2026, 3, 1, 11, 0, 0, tzinfo=JST)

        log.record_action("アイネ", "起床", t1)
        log.record_speech("アイネ", "おはよう", t2)
        log.record_action("クロエ", "登場", t3)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        # Check order
        idx_10_00 = content.index("## 10:00")
        idx_10_30 = content.index("## 10:30")
        idx_11_00 = content.index("## 11:00")
        assert idx_10_00 < idx_10_30 < idx_11_00

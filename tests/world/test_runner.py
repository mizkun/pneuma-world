"""Tests for the World Engine CLI runner."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pneuma_world.models.action import ActionType, ThinkResult
from pneuma_world.models.state import WorldState


class TestParseArgs:
    """CLI argument parsing tests."""

    def test_default_args(self) -> None:
        """Default arguments are applied correctly."""
        from pneuma_world.runner import parse_world_args

        args = parse_world_args([])
        assert args.scenario == "yurucamp"
        assert args.think_interval == 900
        assert args.max_ticks is None
        assert args.dry_run is False

    def test_custom_scenario(self) -> None:
        """--scenario flag sets the scenario name."""
        from pneuma_world.runner import parse_world_args

        args = parse_world_args(["--scenario", "office"])
        assert args.scenario == "office"

    def test_think_interval(self) -> None:
        """--think-interval flag sets think tick interval."""
        from pneuma_world.runner import parse_world_args

        args = parse_world_args(["--think-interval", "30"])
        assert args.think_interval == 30

    def test_max_ticks(self) -> None:
        """--max-ticks flag sets maximum think ticks."""
        from pneuma_world.runner import parse_world_args

        args = parse_world_args(["--max-ticks", "5"])
        assert args.max_ticks == 5

    def test_dry_run(self) -> None:
        """--dry-run flag enables mock LLM mode."""
        from pneuma_world.runner import parse_world_args

        args = parse_world_args(["--dry-run"])
        assert args.dry_run is True


class TestMockLLM:
    """Tests for the dry-run mock LLM adapter."""

    @pytest.mark.asyncio
    async def test_mock_llm_returns_valid_json(self) -> None:
        """MockLLM generates valid ThinkResult-compatible JSON."""
        from pneuma_world.runner import MockLLMAdapter

        mock_llm = MockLLMAdapter()
        from pneuma_core.llm.adapter import LLMRequest

        # Use a system prompt that triggers think response (contains "action_type" and "JSON")
        request = LLMRequest(
            system_prompt='出力形式: JSON形式で action_type を指定してください',
            messages=[{"role": "user", "content": "次の行動を決定してください。"}],
        )
        response = await mock_llm.generate(request)

        import json

        data = json.loads(response.content)
        assert "thought" in data
        assert "action_type" in data
        # action_type should be a valid ActionType value
        valid_actions = {"idle", "move", "solo_activity", "start_conversation", "use_tool"}
        assert data["action_type"] in valid_actions

    @pytest.mark.asyncio
    async def test_mock_llm_model_field(self) -> None:
        """MockLLM response has correct model field."""
        from pneuma_world.runner import MockLLMAdapter

        mock_llm = MockLLMAdapter()
        from pneuma_core.llm.adapter import LLMRequest

        request = LLMRequest(
            system_prompt='出力形式: JSON形式で action_type を指定してください',
            messages=[{"role": "user", "content": "test"}],
        )
        response = await mock_llm.generate(request)
        assert response.model == "mock-dry-run"

    @pytest.mark.asyncio
    async def test_mock_llm_usage_field(self) -> None:
        """MockLLM response has usage field."""
        from pneuma_world.runner import MockLLMAdapter

        mock_llm = MockLLMAdapter()
        from pneuma_core.llm.adapter import LLMRequest

        request = LLMRequest(
            system_prompt='出力形式: JSON形式で action_type を指定してください',
            messages=[{"role": "user", "content": "test"}],
        )
        response = await mock_llm.generate(request)
        assert "input_tokens" in response.usage
        assert "output_tokens" in response.usage


class TestFormatThinkSummary:
    """Tests for the console output formatting."""

    def test_idle_action(self) -> None:
        """Idle action is formatted correctly."""
        from pneuma_world.runner import format_think_summary

        result = ThinkResult(
            thought="静かでいい...",
            action_type=ActionType.IDLE,
        )
        output = format_think_summary("リン", result)
        assert "リン" in output
        assert "静かでいい..." in output
        assert "idle" in output

    def test_move_action(self) -> None:
        """Move action shows target location."""
        from pneuma_world.runner import format_think_summary

        result = ThinkResult(
            thought="本棚に行こう",
            action_type=ActionType.MOVE,
            target_location="bookshelf",
        )
        output = format_think_summary("千明", result)
        assert "千明" in output
        assert "move" in output
        assert "bookshelf" in output

    def test_solo_activity_action(self) -> None:
        """Solo activity action shows detail."""
        from pneuma_world.runner import format_think_summary

        result = ThinkResult(
            thought="読書しよう",
            action_type=ActionType.SOLO_ACTIVITY,
            action_detail="reading",
        )
        output = format_think_summary("リン", result)
        assert "リン" in output
        assert "solo_activity" in output
        assert "reading" in output

    def test_start_conversation_action(self) -> None:
        """Start conversation action shows target."""
        from pneuma_world.runner import format_think_summary

        result = ThinkResult(
            thought="なでしこに話しかけよう",
            action_type=ActionType.START_CONVERSATION,
            target_character_id="nadeshiko-001",
            action_detail="やっほー",
        )
        output = format_think_summary("千明", result)
        assert "千明" in output
        assert "start_conversation" in output


class TestFormatTickHeader:
    """Tests for tick header formatting."""

    def test_tick_header_format(self) -> None:
        """Tick header shows time and tick number."""
        from pneuma_world.runner import format_tick_header

        world_time = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        output = format_tick_header(world_time, 1)
        assert "[" in output
        assert "Think Tick #1" in output


class TestBuildWorldComponents:
    """Tests for component creation."""

    @pytest.mark.asyncio
    async def test_build_creates_engines_for_each_character(self) -> None:
        """build_world_components creates a RuntimeEngine per character."""
        from pneuma_world.runner import MockLLMAdapter, build_world_components

        scenario_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "packages"
            / "pneuma-world"
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "yurucamp"
        )
        llm = MockLLMAdapter()
        embedding = AsyncMock()
        embedding.embed = AsyncMock(return_value=[0.0] * 1536)
        embedding.embed_batch = AsyncMock(return_value=[[0.0] * 1536])

        components = await build_world_components(
            scenario_dir=scenario_dir,
            llm=llm,
            embedding_service=embedding,
            db_path=":memory:",
        )

        # Should have engines for all 3 yurucamp characters
        assert len(components["engines"]) == 3
        assert "nadeshiko-001" in components["engines"]

        # Should have a WorldEngine
        from pneuma_world.engine import WorldEngine

        assert isinstance(components["world_engine"], WorldEngine)

        # Should have character_names mapping
        assert len(components["character_names"]) == 3

        # Cleanup
        for storage in components["storages"]:
            await storage.close()

    @pytest.mark.asyncio
    async def test_build_uses_separate_db(self) -> None:
        """build_world_components uses the specified db_path."""
        from pneuma_world.runner import MockLLMAdapter, build_world_components

        scenario_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "packages"
            / "pneuma-world"
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "yurucamp"
        )
        llm = MockLLMAdapter()
        embedding = AsyncMock()
        embedding.embed = AsyncMock(return_value=[0.0] * 1536)
        embedding.embed_batch = AsyncMock(return_value=[[0.0] * 1536])

        components = await build_world_components(
            scenario_dir=scenario_dir,
            llm=llm,
            embedding_service=embedding,
            db_path=":memory:",
        )

        # All storages should be initialized successfully
        for storage in components["storages"]:
            tables = await storage.list_tables()
            assert "characters" in tables
            await storage.close()


class TestRunWorldDryRun:
    """Integration-level tests for dry-run mode (no real LLM calls)."""

    @pytest.mark.asyncio
    async def test_dry_run_one_tick(self) -> None:
        """Dry-run mode completes one think tick without errors."""
        from pneuma_world.runner import MockLLMAdapter, build_world_components

        scenario_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "packages"
            / "pneuma-world"
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "yurucamp"
        )
        llm = MockLLMAdapter()
        embedding = AsyncMock()
        embedding.embed = AsyncMock(return_value=[0.0] * 1536)
        embedding.embed_batch = AsyncMock(return_value=[[0.0] * 1536])

        components = await build_world_components(
            scenario_dir=scenario_dir,
            llm=llm,
            embedding_service=embedding,
            db_path=":memory:",
        )

        world_engine = components["world_engine"]

        # Advance until we get a think tick (with think_interval=1, first tick fires immediately)
        # The clock was configured with think_interval_seconds from the TickConfig
        # We need to advance enough visual ticks
        from pneuma_world.clock import TickConfig, WorldClock

        # Create a fast clock for testing
        fast_clock = WorldClock(TickConfig(
            visual_interval_seconds=1.0,
            think_interval_seconds=1.0,  # Think on every visual tick
        ))
        world_engine._clock = fast_clock

        results = await world_engine.tick()
        # First visual tick: think fires (1 second elapsed = 1 think interval)
        assert isinstance(results, list)
        # Results should contain ThinkResults for characters not in conversation
        assert len(results) == 3  # All 3 characters should think

        for result in results:
            assert isinstance(result, ThinkResult)
            assert result.thought != ""

        # Cleanup
        for storage in components["storages"]:
            await storage.close()

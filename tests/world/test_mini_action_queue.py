"""Tests for mini action queue (#4)."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pneuma_core.llm.adapter import LLMRequest, LLMResponse
from pneuma_world.models.action import ActionType, MiniAction, ThinkResult
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, WorldState
from pneuma_world.think_cycle import ThinkCycle, _parse_think_response
from pneuma_world.tools import ToolRegistry
from pneuma_world.world_log import WorldLog

JST = timezone(timedelta(hours=9))


def _make_world_state() -> WorldState:
    return WorldState(
        tick=1,
        world_time=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
        characters={
            "aine": CharacterState(
                character_id="aine",
                location="clubroom",
                position=Position(100, 100),
                activity="idle",
            ),
        },
        active_conversations=[],
        locations={
            "clubroom": Location(
                id="clubroom",
                name="部室",
                bounds=(Position(0, 0), Position(200, 200)),
            ),
        },
    )


def _make_llm_response(data: dict) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(data, ensure_ascii=False),
        model="claude-haiku-4-5-20251001",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


class TestMiniAction:
    """Tests for MiniAction dataclass."""

    def test_create_mini_action(self) -> None:
        action = MiniAction(
            action="walk_to",
            target="bookshelf_01",
            animation="walking",
            duration=5,
        )
        assert action.action == "walk_to"
        assert action.target == "bookshelf_01"
        assert action.animation == "walking"
        assert action.duration == 5

    def test_mini_action_fields(self) -> None:
        field_names = {f.name for f in fields(MiniAction)}
        assert field_names == {"action", "target", "animation", "duration"}

    def test_mini_action_optional_target(self) -> None:
        """target should accept empty string for no target."""
        action = MiniAction(action="idle_animation", target="", animation="yawn", duration=3)
        assert action.target == ""

    def test_mini_action_optional_animation(self) -> None:
        """animation should accept empty string for no animation."""
        action = MiniAction(action="sit", target="chair_01", animation="", duration=10)
        assert action.animation == ""


class TestThinkResultActionQueue:
    """Tests for ThinkResult with action_queue field."""

    def test_think_result_has_action_queue_field(self) -> None:
        result = ThinkResult(
            thought="テスト",
            action_type=ActionType.IDLE,
        )
        assert hasattr(result, "action_queue")

    def test_action_queue_defaults_to_empty_list(self) -> None:
        result = ThinkResult(
            thought="テスト",
            action_type=ActionType.IDLE,
        )
        assert result.action_queue == []

    def test_action_queue_with_mini_actions(self) -> None:
        actions = [
            MiniAction(action="walk_to", target="desk_01", animation="walking", duration=3),
            MiniAction(action="sit", target="desk_01", animation="sitting", duration=10),
        ]
        result = ThinkResult(
            thought="テスト",
            action_type=ActionType.SOLO_ACTIVITY,
            action_queue=actions,
        )
        assert len(result.action_queue) == 2
        assert result.action_queue[0].action == "walk_to"
        assert result.action_queue[1].action == "sit"

    def test_backward_compatibility_without_action_queue(self) -> None:
        """Existing code that doesn't pass action_queue should still work."""
        result = ThinkResult(
            thought="後方互換",
            action_type=ActionType.MOVE,
            target_location="hallway",
        )
        assert result.action_queue == []
        assert result.target_location == "hallway"


class TestParseThinkResponseActionQueue:
    """Tests for _parse_think_response with action_queue."""

    def test_parse_with_action_queue(self) -> None:
        content = json.dumps({
            "thought": "本棚に行って本を読もう",
            "action_type": "solo_activity",
            "action_detail": "読書",
            "action_queue": [
                {"action": "walk_to", "target": "bookshelf_01", "animation": "walking", "duration": 3},
                {"action": "interact", "target": "bookshelf_01", "animation": "reaching", "duration": 2},
                {"action": "sit", "target": "chair_01", "animation": "sitting", "duration": 30},
            ],
        }, ensure_ascii=False)

        result = _parse_think_response(content)

        assert result.thought == "本棚に行って本を読もう"
        assert result.action_type == ActionType.SOLO_ACTIVITY
        assert len(result.action_queue) == 3
        assert result.action_queue[0].action == "walk_to"
        assert result.action_queue[0].target == "bookshelf_01"
        assert result.action_queue[0].animation == "walking"
        assert result.action_queue[0].duration == 3
        assert result.action_queue[1].action == "interact"
        assert result.action_queue[2].action == "sit"
        assert result.action_queue[2].duration == 30

    def test_parse_without_action_queue(self) -> None:
        """Backward compatibility: JSON without action_queue should parse fine."""
        content = json.dumps({
            "thought": "何もしない",
            "action_type": "idle",
        }, ensure_ascii=False)

        result = _parse_think_response(content)

        assert result.action_type == ActionType.IDLE
        assert result.action_queue == []

    def test_parse_with_invalid_action_queue_falls_back_to_empty(self) -> None:
        """When action_queue is not a list, fall back to empty list."""
        content = json.dumps({
            "thought": "テスト",
            "action_type": "idle",
            "action_queue": "invalid_string",
        }, ensure_ascii=False)

        result = _parse_think_response(content)

        assert result.action_type == ActionType.IDLE
        assert result.action_queue == []

    def test_parse_with_malformed_action_queue_items_falls_back(self) -> None:
        """When action_queue items are missing required fields, fall back to empty list."""
        content = json.dumps({
            "thought": "テスト",
            "action_type": "idle",
            "action_queue": [
                {"action": "walk_to"},  # missing target, animation, duration
            ],
        }, ensure_ascii=False)

        result = _parse_think_response(content)

        assert result.action_type == ActionType.IDLE
        assert result.action_queue == []

    def test_parse_with_empty_action_queue(self) -> None:
        """Empty action_queue list should be preserved."""
        content = json.dumps({
            "thought": "テスト",
            "action_type": "idle",
            "action_queue": [],
        }, ensure_ascii=False)

        result = _parse_think_response(content)

        assert result.action_queue == []


class TestThinkCyclePromptActionQueue:
    """Tests for ThinkCycle prompt containing action_queue instructions."""

    @pytest.mark.asyncio
    async def test_prompt_contains_action_queue_instruction(self, tmp_path: Path) -> None:
        """System prompt should instruct LLM to output action_queue."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "テスト",
            "action_type": "idle",
            "action_queue": [],
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        call_args = mock_llm.generate.call_args
        request = call_args[0][0] if call_args[0] else call_args[1].get("request")
        assert isinstance(request, LLMRequest)
        assert "action_queue" in request.system_prompt

    @pytest.mark.asyncio
    async def test_prompt_contains_multi_step_instruction(self, tmp_path: Path) -> None:
        """System prompt should instruct LLM to generate multiple action steps."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "テスト",
            "action_type": "idle",
            "action_queue": [],
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        call_args = mock_llm.generate.call_args
        request = call_args[0][0] if call_args[0] else call_args[1].get("request")
        # The prompt should mention generating multiple steps/actions
        assert "複数ステップ" in request.system_prompt or "複数" in request.system_prompt

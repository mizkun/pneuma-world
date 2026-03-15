"""Tests for ThinkCycle with character context (personality, goals, think history).

Issue #109: ThinkCycle にキャラクター性格・口調・思考履歴を接続する
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pneuma_core.llm.adapter import LLMRequest, LLMResponse
from pneuma_core.models.character import Character
from pneuma_core.models.emotion import EmotionalState
from pneuma_core.models.goals import GoalTree, Objective, Task, Vision
from pneuma_core.models.personality import Personality
from pneuma_core.models.values import Values
from pneuma_world.models.action import ActionType, ThinkResult
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, WorldState
from pneuma_world.think_cycle import ThinkCycle
from pneuma_world.tools import ToolRegistry
from pneuma_world.world_log import WorldLog

JST = timezone(timedelta(hours=9))


# --- Fixtures ---


def _make_character(
    char_id: str = "rin-001",
    name: str = "志摩リン",
    speaking_style: str | None = "短めの文、落ち着いたトーン。「〜だね」「〜かな」が多い。",
) -> Character:
    """Create a test Character with personality and speaking style."""
    return Character(
        id=char_id,
        name=name,
        personality=Personality(
            openness=0.75,
            conscientiousness=0.8,
            extraversion=0.2,
            agreeableness=0.55,
            neuroticism=0.2,
        ),
        values=Values(
            self_transcendence=0.4,
            self_enhancement=0.3,
            openness_to_change=0.7,
            conservation=0.65,
        ),
        profile="ソロキャンプを愛する寡黙な女の子。",
        speaking_style=speaking_style,
        personality_description="寡黙で落ち着いた性格。一人の時間を大切にする。",
        values_description="自分のペースを大切にすること。",
        background="祖父の影響でソロキャンプを楽しんでいる。",
    )


def _make_goal_tree(char_id: str = "rin-001") -> GoalTree:
    """Create a test GoalTree."""
    vision = Vision(id="v1", character_id=char_id, content="自分のペースでキャンプを楽しむ")
    objective = Objective(
        id="o1",
        character_id=char_id,
        vision_id="v1",
        content="新しいキャンプ場を開拓する",
        status="active",
        progress=0.4,
    )
    task = Task(
        id="t1",
        character_id=char_id,
        objective_id="o1",
        content="次のソロキャンプの計画を立てる",
        status="in_progress",
    )
    return GoalTree(visions=[vision], objectives=[objective], tasks=[task])


def _make_emotional_state() -> EmotionalState:
    return EmotionalState(
        pleasure=0.3,
        arousal=-0.2,
        dominance=0.3,
        emotion_label="落ち着き",
        situation="部室で本を読んでいる",
    )


def _make_world_state(
    *,
    characters: dict[str, CharacterState] | None = None,
) -> WorldState:
    """Helper to create a WorldState."""
    default_chars = {
        "rin-001": CharacterState(
            character_id="rin-001",
            location="clubroom",
            position=Position(100, 100),
            activity="読書をしている",
        ),
        "nadeshiko-001": CharacterState(
            character_id="nadeshiko-001",
            location="clubroom",
            position=Position(150, 100),
            activity="idle",
        ),
    }
    return WorldState(
        tick=1,
        world_time=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
        characters=characters or default_chars,
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


def _make_think_cycle_with_characters(
    mock_llm: AsyncMock,
    tmp_path: Path,
    characters: dict[str, Character] | None = None,
    goal_trees: dict[str, GoalTree] | None = None,
    initial_emotions: dict[str, EmotionalState] | None = None,
    character_names: dict[str, str] | None = None,
) -> ThinkCycle:
    """Create a ThinkCycle with character context."""
    return ThinkCycle(
        llm=mock_llm,
        tool_registry=ToolRegistry(),
        world_log=WorldLog(log_dir=tmp_path),
        characters=characters,
        goal_trees=goal_trees,
        initial_emotions=initial_emotions,
        character_names=character_names,
    )


# === Test: System prompt includes personality ===


class TestThinkCyclePersonality:
    """ThinkCycle should include character personality in prompts."""

    @pytest.mark.asyncio
    async def test_prompt_includes_personality_traits(self, tmp_path: Path) -> None:
        """When Character is provided, personality traits appear in system prompt."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "静かでいい...",
            "action_type": "idle",
        })

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
        )

        await cycle.execute("rin-001", "志摩リン", _make_world_state())

        request: LLMRequest = mock_llm.generate.call_args[0][0]
        prompt = request.system_prompt
        # Should include personality section with trait labels
        assert "性格" in prompt
        assert "外向性" in prompt  # extraversion 0.2 = low

    @pytest.mark.asyncio
    async def test_prompt_includes_speaking_style(self, tmp_path: Path) -> None:
        """Speaking style from Character YAML appears in system prompt."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "ん...",
            "action_type": "idle",
        })

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
        )

        await cycle.execute("rin-001", "志摩リン", _make_world_state())

        request: LLMRequest = mock_llm.generate.call_args[0][0]
        prompt = request.system_prompt
        assert "口調" in prompt
        assert "短めの文" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_profile(self, tmp_path: Path) -> None:
        """Character profile/background appears in system prompt."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "...",
            "action_type": "idle",
        })

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
        )

        await cycle.execute("rin-001", "志摩リン", _make_world_state())

        request: LLMRequest = mock_llm.generate.call_args[0][0]
        prompt = request.system_prompt
        assert "ソロキャンプ" in prompt


# === Test: System prompt includes goals ===


class TestThinkCycleGoals:
    """ThinkCycle should include character goals in prompts."""

    @pytest.mark.asyncio
    async def test_prompt_includes_goals(self, tmp_path: Path) -> None:
        """GoalTree is rendered in system prompt."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "キャンプの計画を立てよう",
            "action_type": "idle",
        })

        rin = _make_character()
        goals = _make_goal_tree()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
            goal_trees={"rin-001": goals},
        )

        await cycle.execute("rin-001", "志摩リン", _make_world_state())

        request: LLMRequest = mock_llm.generate.call_args[0][0]
        prompt = request.system_prompt
        assert "目標" in prompt
        assert "キャンプ場を開拓" in prompt


# === Test: System prompt includes emotional state ===


class TestThinkCycleEmotion:
    """ThinkCycle should include emotional state in prompts."""

    @pytest.mark.asyncio
    async def test_prompt_includes_emotional_state(self, tmp_path: Path) -> None:
        """EmotionalState is rendered in system prompt."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "落ち着く...",
            "action_type": "idle",
        })

        rin = _make_character()
        emotion = _make_emotional_state()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
            initial_emotions={"rin-001": emotion},
        )

        await cycle.execute("rin-001", "志摩リン", _make_world_state())

        request: LLMRequest = mock_llm.generate.call_args[0][0]
        prompt = request.system_prompt
        assert "感情" in prompt
        assert "落ち着き" in prompt


# === Test: Think history ===


class TestThinkCycleHistory:
    """ThinkCycle should track and include recent think history."""

    @pytest.mark.asyncio
    async def test_second_tick_includes_previous_thought(self, tmp_path: Path) -> None:
        """After first tick, second tick's prompt includes previous thought."""
        mock_llm = AsyncMock()
        # First tick response
        mock_llm.generate.side_effect = [
            _make_llm_response({
                "thought": "お腹すいたなぁ",
                "action_type": "idle",
            }),
            _make_llm_response({
                "thought": "やっぱり何か食べよう",
                "action_type": "solo_activity",
                "action_detail": "お弁当を食べる",
            }),
        ]

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
        )
        world_state = _make_world_state()

        # First tick
        await cycle.execute("rin-001", "志摩リン", world_state)

        # Second tick
        await cycle.execute("rin-001", "志摩リン", world_state)

        # Check second call's prompt includes first thought
        second_request: LLMRequest = mock_llm.generate.call_args_list[1][0][0]
        prompt = second_request.system_prompt
        assert "お腹すいたなぁ" in prompt

    @pytest.mark.asyncio
    async def test_think_history_limited_to_max(self, tmp_path: Path) -> None:
        """Think history should not grow unbounded."""
        mock_llm = AsyncMock()
        # Create many responses
        responses = [
            _make_llm_response({
                "thought": f"思考 {i}",
                "action_type": "idle",
            })
            for i in range(12)
        ]
        mock_llm.generate.side_effect = responses

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
        )
        world_state = _make_world_state()

        # Execute many ticks
        for _ in range(12):
            await cycle.execute("rin-001", "志摩リン", world_state)

        # History should be capped (default max 10)
        last_request: LLMRequest = mock_llm.generate.call_args_list[-1][0][0]
        prompt = last_request.system_prompt
        # Oldest thoughts should have been dropped
        assert "思考 0" not in prompt
        # Recent thoughts should be present
        assert "思考 10" in prompt

    @pytest.mark.asyncio
    async def test_history_includes_action_type(self, tmp_path: Path) -> None:
        """Think history should show both thought and action."""
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = [
            _make_llm_response({
                "thought": "散歩したいな",
                "action_type": "move",
                "target_location": "hallway",
            }),
            _make_llm_response({
                "thought": "...",
                "action_type": "idle",
            }),
        ]

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
        )
        world_state = _make_world_state()

        await cycle.execute("rin-001", "志摩リン", world_state)
        await cycle.execute("rin-001", "志摩リン", world_state)

        second_request: LLMRequest = mock_llm.generate.call_args_list[1][0][0]
        prompt = second_request.system_prompt
        assert "散歩したいな" in prompt
        assert "move" in prompt


# === Test: Nearby characters shown by name ===


class TestThinkCycleNearbyNames:
    """Nearby characters should be shown by name, not ID."""

    @pytest.mark.asyncio
    async def test_nearby_characters_shown_by_name(self, tmp_path: Path) -> None:
        """When character_names is provided, nearby chars appear as names."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "なでしこがいるな",
            "action_type": "idle",
        })

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
            character_names={
                "rin-001": "志摩リン",
                "nadeshiko-001": "各務原なでしこ",
            },
        )
        world_state = _make_world_state()

        await cycle.execute("rin-001", "志摩リン", world_state)

        request: LLMRequest = mock_llm.generate.call_args[0][0]
        prompt = request.system_prompt
        # Should show name, not ID
        assert "各務原なでしこ" in prompt
        # Should NOT show raw ID
        assert "nadeshiko-001" not in prompt


# === Test: Backward compatibility ===


class TestThinkCycleBackwardCompatibility:
    """ThinkCycle without character context should work as before."""

    @pytest.mark.asyncio
    async def test_no_characters_still_works(self, tmp_path: Path) -> None:
        """When no characters provided, falls back to minimal prompt."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "何もない",
            "action_type": "idle",
        })

        # No characters parameter — backward compatible
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=WorldLog(log_dir=tmp_path),
        )
        world_state = _make_world_state()

        result = await cycle.execute("rin-001", "志摩リン", world_state)

        assert result.action_type == ActionType.IDLE
        assert result.thought == "何もない"

    @pytest.mark.asyncio
    async def test_unknown_character_id_falls_back(self, tmp_path: Path) -> None:
        """When character ID is not in the characters dict, falls back gracefully."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "...",
            "action_type": "idle",
        })

        rin = _make_character()
        cycle = _make_think_cycle_with_characters(
            mock_llm,
            tmp_path,
            characters={"rin-001": rin},
        )
        world_state = _make_world_state()

        # Execute with an ID not in characters dict
        result = await cycle.execute("unknown-001", "不明キャラ", world_state)

        assert result.action_type == ActionType.IDLE

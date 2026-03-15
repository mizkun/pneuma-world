"""Tests for WorldEngine: the top-level orchestrator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pneuma_world.clock import TickConfig, WorldClock
from pneuma_world.engine import WorldEngine
from pneuma_world.interaction_bus import InteractionBus
from pneuma_world.models.action import ActionType, ThinkResult
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, Conversation, WorldState
from pneuma_world.think_cycle import ThinkCycle
from pneuma_world.world_log import WorldLog

JST = timezone(timedelta(hours=9))

# --- Helpers ---


def _make_world_state(
    *,
    characters: dict[str, CharacterState] | None = None,
    tick: int = 0,
) -> WorldState:
    """Create a WorldState for testing."""
    default_chars = {
        "aine": CharacterState(
            character_id="aine",
            location="clubroom",
            position=Position(100, 100),
            activity="idle",
        ),
        "chloe": CharacterState(
            character_id="chloe",
            location="clubroom",
            position=Position(150, 100),
            activity="idle",
        ),
    }
    return WorldState(
        tick=tick,
        world_time=datetime(2026, 3, 1, 10, 0, 0, tzinfo=JST),
        characters=characters or default_chars,
        active_conversations=[],
        locations={
            "clubroom": Location(
                id="clubroom",
                name="部室",
                bounds=(Position(0, 0), Position(200, 200)),
            ),
            "hallway": Location(
                id="hallway",
                name="廊下",
                bounds=(Position(200, 0), Position(400, 200)),
            ),
        },
    )


def _make_character_names() -> dict[str, str]:
    return {"aine": "アイネ", "chloe": "クロエ"}


def _make_engine(
    world_state: WorldState | None = None,
    tmp_path: Path | None = None,
    tick_config: TickConfig | None = None,
) -> tuple[WorldEngine, AsyncMock, AsyncMock]:
    """Create a WorldEngine with mock ThinkCycle and InteractionBus.

    Returns (engine, mock_think_cycle, mock_interaction_bus).
    """
    ws = world_state or _make_world_state()
    clock = WorldClock(config=tick_config or TickConfig())
    mock_think_cycle = AsyncMock(spec=ThinkCycle)
    mock_interaction_bus = AsyncMock(spec=InteractionBus)
    log_dir = tmp_path or Path("/tmp/test-world-log")
    world_log = WorldLog(log_dir=log_dir)

    engine = WorldEngine(
        world_state=ws,
        clock=clock,
        think_cycle=mock_think_cycle,
        interaction_bus=mock_interaction_bus,
        world_log=world_log,
        character_names=_make_character_names(),
    )
    return engine, mock_think_cycle, mock_interaction_bus


# --- WorldEngine Tests ---


class TestWorldEngineState:
    """Tests for WorldEngine.state property."""

    def test_state_returns_world_state(self) -> None:
        ws = _make_world_state()
        engine, _, _ = _make_engine(world_state=ws)

        assert engine.state is ws

    def test_state_has_characters(self) -> None:
        ws = _make_world_state()
        engine, _, _ = _make_engine(world_state=ws)

        assert "aine" in engine.state.characters
        assert "chloe" in engine.state.characters


class TestWorldEngineTick:
    """Tests for WorldEngine.tick method."""

    @pytest.mark.asyncio
    async def test_visual_tick_without_think(self, tmp_path: Path) -> None:
        """Visual tick that doesn't trigger a think tick should return empty."""
        # visual_interval=1.0, think_interval=10.0
        # First visual tick at t=1s, think at t=10s
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=10.0)
        engine, mock_think, _ = _make_engine(tick_config=config, tmp_path=tmp_path)

        results = await engine.tick()

        assert results == []
        mock_think.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_think_tick_fires_think_cycle(self, tmp_path: Path) -> None:
        """When think tick fires, ThinkCycle should execute for each character."""
        # Set intervals so think fires on first visual tick
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, _ = _make_engine(tick_config=config, tmp_path=tmp_path)

        mock_think.execute.return_value = ThinkResult(
            thought="暇だな",
            action_type=ActionType.IDLE,
        )

        results = await engine.tick()

        # Should have executed think for each character (2 characters)
        assert mock_think.execute.call_count == 2
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_think_tick_returns_think_results(self, tmp_path: Path) -> None:
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, _ = _make_engine(tick_config=config, tmp_path=tmp_path)

        idle_result = ThinkResult(
            thought="暇だな",
            action_type=ActionType.IDLE,
        )
        mock_think.execute.return_value = idle_result

        results = await engine.tick()

        for result in results:
            assert isinstance(result, ThinkResult)
            assert result.action_type == ActionType.IDLE

    @pytest.mark.asyncio
    async def test_skips_characters_in_conversation(self, tmp_path: Path) -> None:
        """Characters already in conversation should not think."""
        chars = {
            "aine": CharacterState(
                character_id="aine",
                location="clubroom",
                position=Position(100, 100),
                activity="talking",
                conversation_id="conv-1",
            ),
            "chloe": CharacterState(
                character_id="chloe",
                location="clubroom",
                position=Position(150, 100),
                activity="idle",
            ),
        }
        ws = _make_world_state(characters=chars)
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, _ = _make_engine(
            world_state=ws, tick_config=config, tmp_path=tmp_path,
        )

        mock_think.execute.return_value = ThinkResult(
            thought="暇",
            action_type=ActionType.IDLE,
        )

        results = await engine.tick()

        # Only chloe should think (aine is in conversation)
        assert mock_think.execute.call_count == 1
        call_args = mock_think.execute.call_args[0]
        assert call_args[0] == "chloe"  # character_id

    @pytest.mark.asyncio
    async def test_visual_tick_interpolates_positions(self, tmp_path: Path) -> None:
        """Characters with target_position should move during visual ticks."""
        chars = {
            "aine": CharacterState(
                character_id="aine",
                location="clubroom",
                position=Position(100, 100),
                activity="walking",
                target_position=Position(200, 100),
            ),
        }
        ws = _make_world_state(characters=chars)
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=100.0)
        engine, _, _ = _make_engine(
            world_state=ws, tick_config=config, tmp_path=tmp_path,
        )

        await engine.tick()

        # Position should have changed toward target
        new_pos = engine.state.characters["aine"].position
        assert new_pos.x > 100  # moved toward target


class TestApplyThinkResult:
    """Tests for WorldEngine.apply_think_result."""

    def test_apply_idle(self, tmp_path: Path) -> None:
        """IDLE should not change state."""
        engine, _, _ = _make_engine(tmp_path=tmp_path)
        original_activity = engine.state.characters["aine"].activity

        engine.apply_think_result(
            "aine",
            ThinkResult(thought="暇", action_type=ActionType.IDLE),
        )

        assert engine.state.characters["aine"].activity == original_activity

    def test_apply_move(self, tmp_path: Path) -> None:
        """MOVE should set target_position and change activity."""
        engine, _, _ = _make_engine(tmp_path=tmp_path)

        engine.apply_think_result(
            "aine",
            ThinkResult(
                thought="廊下に行こう",
                action_type=ActionType.MOVE,
                action_detail="廊下に向かう",
                target_location="hallway",
            ),
        )

        char = engine.state.characters["aine"]
        assert char.target_position is not None
        assert char.activity == "walking"

    def test_apply_solo_activity(self, tmp_path: Path) -> None:
        """SOLO_ACTIVITY should change activity."""
        engine, _, _ = _make_engine(tmp_path=tmp_path)

        engine.apply_think_result(
            "aine",
            ThinkResult(
                thought="読書しよう",
                action_type=ActionType.SOLO_ACTIVITY,
                action_detail="読書をしている",
            ),
        )

        assert engine.state.characters["aine"].activity == "読書をしている"

    def test_apply_start_conversation(self, tmp_path: Path) -> None:
        """START_CONVERSATION should update both characters' activity to 'talking'."""
        engine, _, _ = _make_engine(tmp_path=tmp_path)

        engine.apply_think_result(
            "aine",
            ThinkResult(
                thought="クロエに話しかけよう",
                action_type=ActionType.START_CONVERSATION,
                action_detail="挨拶する",
                target_character_id="chloe",
            ),
        )

        assert engine.state.characters["aine"].activity == "talking"
        assert engine.state.characters["chloe"].activity == "talking"
        # Both should have the same conversation_id
        assert engine.state.characters["aine"].conversation_id is not None
        assert (
            engine.state.characters["aine"].conversation_id
            == engine.state.characters["chloe"].conversation_id
        )

    def test_apply_start_conversation_adds_to_active(self, tmp_path: Path) -> None:
        """START_CONVERSATION should add a Conversation to active_conversations."""
        engine, _, _ = _make_engine(tmp_path=tmp_path)

        engine.apply_think_result(
            "aine",
            ThinkResult(
                thought="クロエに話しかけよう",
                action_type=ActionType.START_CONVERSATION,
                target_character_id="chloe",
            ),
        )

        assert len(engine.state.active_conversations) == 1
        conv = engine.state.active_conversations[0]
        assert "aine" in conv.participant_ids
        assert "chloe" in conv.participant_ids

    def test_apply_use_tool(self, tmp_path: Path) -> None:
        """USE_TOOL should change activity."""
        engine, _, _ = _make_engine(tmp_path=tmp_path)

        engine.apply_think_result(
            "aine",
            ThinkResult(
                thought="ブログを書こう",
                action_type=ActionType.USE_TOOL,
                action_detail="ブログ執筆中",
                tool_name="blog_write",
                tool_input="今日の出来事",
            ),
        )

        assert engine.state.characters["aine"].activity == "ブログ執筆中"


class TestWorldEngineThinkAndApply:
    """Integration tests: tick triggers think, results get applied."""

    @pytest.mark.asyncio
    async def test_move_result_sets_target_position(self, tmp_path: Path) -> None:
        """A MOVE ThinkResult should cause the character to start moving."""
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, _ = _make_engine(tick_config=config, tmp_path=tmp_path)

        mock_think.execute.return_value = ThinkResult(
            thought="廊下に行こう",
            action_type=ActionType.MOVE,
            action_detail="廊下に向かう",
            target_location="hallway",
        )

        await engine.tick()

        # Both characters should now have target_position set
        # (since both go through ThinkCycle)
        for char_id in ["aine", "chloe"]:
            char = engine.state.characters[char_id]
            assert char.activity == "walking"
            assert char.target_position is not None

    @pytest.mark.asyncio
    async def test_start_conversation_triggers_interaction_bus(
        self, tmp_path: Path
    ) -> None:
        """START_CONVERSATION should trigger InteractionBus.start_conversation."""
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, mock_bus = _make_engine(
            tick_config=config, tmp_path=tmp_path,
        )

        # aine wants to start conversation, chloe just idles
        async def think_side_effect(char_id, char_name, world_state):
            if char_id == "aine":
                return ThinkResult(
                    thought="クロエに話しかけよう",
                    action_type=ActionType.START_CONVERSATION,
                    action_detail="挨拶する",
                    target_character_id="chloe",
                )
            return ThinkResult(
                thought="暇",
                action_type=ActionType.IDLE,
            )

        mock_think.execute.side_effect = think_side_effect
        mock_bus.run_conversation.return_value = [
            ("aine", "おはよう！"),
            ("chloe", "おはよう、アイネ！"),
        ]

        await engine.tick()

        # InteractionBus should have been called
        mock_bus.run_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversation_cleanup_after_run_conversation(
        self, tmp_path: Path
    ) -> None:
        """After run_conversation completes, both characters should be reset
        to idle with conversation_id=None, and the Conversation should be
        removed from active_conversations."""
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, mock_bus = _make_engine(
            tick_config=config, tmp_path=tmp_path,
        )

        # aine starts conversation with chloe; chloe idles
        async def think_side_effect(char_id, char_name, world_state):
            if char_id == "aine":
                return ThinkResult(
                    thought="クロエに話しかけよう",
                    action_type=ActionType.START_CONVERSATION,
                    action_detail="挨拶する",
                    target_character_id="chloe",
                )
            return ThinkResult(
                thought="暇",
                action_type=ActionType.IDLE,
            )

        mock_think.execute.side_effect = think_side_effect
        mock_bus.run_conversation.return_value = [
            ("aine", "おはよう！"),
            ("chloe", "おはよう、アイネ！"),
        ]

        await engine.tick()

        # After conversation completes, characters must be cleaned up
        aine = engine.state.characters["aine"]
        chloe = engine.state.characters["chloe"]

        assert aine.conversation_id is None, (
            "aine's conversation_id should be reset to None after conversation"
        )
        assert aine.activity == "idle", (
            "aine's activity should be reset to 'idle' after conversation"
        )
        assert chloe.conversation_id is None, (
            "chloe's conversation_id should be reset to None after conversation"
        )
        assert chloe.activity == "idle", (
            "chloe's activity should be reset to 'idle' after conversation"
        )
        assert len(engine.state.active_conversations) == 0, (
            "active_conversations should be empty after conversation ends"
        )

    @pytest.mark.asyncio
    async def test_characters_eligible_for_think_after_conversation(
        self, tmp_path: Path
    ) -> None:
        """Characters that finished a conversation should be eligible for
        think on the next tick (not permanently skipped)."""
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, mock_bus = _make_engine(
            tick_config=config, tmp_path=tmp_path,
        )

        # First tick: aine starts conversation
        call_count = 0

        async def think_side_effect(char_id, char_name, world_state):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First tick
                if char_id == "aine":
                    return ThinkResult(
                        thought="クロエに話しかけよう",
                        action_type=ActionType.START_CONVERSATION,
                        action_detail="挨拶する",
                        target_character_id="chloe",
                    )
            return ThinkResult(
                thought="暇",
                action_type=ActionType.IDLE,
            )

        mock_think.execute.side_effect = think_side_effect
        mock_bus.run_conversation.return_value = [
            ("aine", "おはよう！"),
            ("chloe", "おはよう、アイネ！"),
        ]

        await engine.tick()  # Conversation starts and completes

        # Reset mock to track second tick calls
        mock_think.execute.reset_mock()
        mock_think.execute.side_effect = None
        mock_think.execute.return_value = ThinkResult(
            thought="暇だな",
            action_type=ActionType.IDLE,
        )

        await engine.tick()  # Second think tick

        # Both characters should be eligible for think again
        assert mock_think.execute.call_count == 2, (
            "Both characters should think on the next tick after conversation ends"
        )

    @pytest.mark.asyncio
    async def test_tick_advances_world_time(self, tmp_path: Path) -> None:
        """Each tick should advance world_time based on think_interval."""
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, _ = _make_engine(tick_config=config, tmp_path=tmp_path)

        mock_think.execute.return_value = ThinkResult(
            thought="暇",
            action_type=ActionType.IDLE,
        )

        original_time = engine.state.world_time
        await engine.tick()

        # world_time should have advanced
        assert engine.state.world_time > original_time

    @pytest.mark.asyncio
    async def test_tick_increments_tick_count(self, tmp_path: Path) -> None:
        """Tick should increment the world state tick counter on think ticks."""
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        engine, mock_think, _ = _make_engine(tick_config=config, tmp_path=tmp_path)

        mock_think.execute.return_value = ThinkResult(
            thought="暇",
            action_type=ActionType.IDLE,
        )

        assert engine.state.tick == 0
        await engine.tick()
        assert engine.state.tick == 1


class TestWorldEngineMovement:
    """Tests for position interpolation during visual ticks."""

    @pytest.mark.asyncio
    async def test_character_reaches_target(self, tmp_path: Path) -> None:
        """After enough ticks, character should reach target position."""
        chars = {
            "aine": CharacterState(
                character_id="aine",
                location="clubroom",
                position=Position(100, 100),
                activity="walking",
                target_position=Position(102, 100),
            ),
        }
        ws = _make_world_state(characters=chars)
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1000.0)
        engine, _, _ = _make_engine(
            world_state=ws, tick_config=config, tmp_path=tmp_path,
        )

        # Speed is 1.0 per tick, distance is 2, so after 2 ticks should arrive
        await engine.tick()
        await engine.tick()

        char = engine.state.characters["aine"]
        assert char.position == Position(102, 100)
        # target_position should be cleared after arrival
        assert char.target_position is None

    @pytest.mark.asyncio
    async def test_stationary_character_unchanged(self, tmp_path: Path) -> None:
        """Characters without target_position should not move."""
        ws = _make_world_state()
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1000.0)
        engine, _, _ = _make_engine(
            world_state=ws, tick_config=config, tmp_path=tmp_path,
        )

        original_pos = engine.state.characters["aine"].position
        await engine.tick()

        assert engine.state.characters["aine"].position == original_pos

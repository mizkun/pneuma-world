"""Tests for ThinkCycle with mock LLM."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pneuma_core.llm.adapter import LLMRequest, LLMResponse
from pneuma_world.models.action import ActionType, ThinkResult
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, WorldState
from pneuma_world.think_cycle import ThinkCycle
from pneuma_world.tools import ToolDefinition, ToolRegistry
from pneuma_world.world_log import WorldLog

JST = timezone(timedelta(hours=9))


def _make_world_state(
    *,
    characters: dict[str, CharacterState] | None = None,
    tick: int = 1,
) -> WorldState:
    """Helper to create a WorldState for testing."""
    default_chars = {
        "aine": CharacterState(
            character_id="aine",
            location="clubroom",
            position=Position(100, 100),
            activity="idle",
        ),
    }
    return WorldState(
        tick=tick,
        world_time=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
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


def _make_llm_response(think_result_dict: dict) -> LLMResponse:
    """Create a mock LLM response from a ThinkResult-like dict."""
    return LLMResponse(
        content=json.dumps(think_result_dict, ensure_ascii=False),
        model="claude-haiku-4-5-20251001",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


def _make_llm_response_with_markdown(think_result_dict: dict) -> LLMResponse:
    """Create a mock LLM response wrapped in markdown code block."""
    json_str = json.dumps(think_result_dict, ensure_ascii=False)
    return LLMResponse(
        content=f"```json\n{json_str}\n```",
        model="claude-haiku-4-5-20251001",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


class TestThinkCycleIdle:
    """Tests for ThinkCycle returning IDLE action."""

    @pytest.mark.asyncio
    async def test_idle_action(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "特にやることがない",
            "action_type": "idle",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.IDLE
        assert result.thought == "特にやることがない"

    @pytest.mark.asyncio
    async def test_idle_logs_thought(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "ぼーっとしている",
            "action_type": "idle",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        log_file = tmp_path / "2026-03-01.md"
        assert log_file.exists()
        content = log_file.read_text()
        assert "[アイネ] (ぼーっとしている)" in content


class TestThinkCycleMove:
    """Tests for ThinkCycle returning MOVE action."""

    @pytest.mark.asyncio
    async def test_move_action(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "廊下に行こう",
            "action_type": "move",
            "action_detail": "廊下に向かう",
            "target_location": "hallway",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.MOVE
        assert result.target_location == "hallway"
        assert result.action_detail == "廊下に向かう"

    @pytest.mark.asyncio
    async def test_move_logs_action(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "廊下に行こう",
            "action_type": "move",
            "action_detail": "廊下に向かう",
            "target_location": "hallway",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        assert "[アイネ]" in content
        assert "廊下に向かう" in content


class TestThinkCycleSoloActivity:
    """Tests for ThinkCycle returning SOLO_ACTIVITY action."""

    @pytest.mark.asyncio
    async def test_solo_activity(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "コードを書こう",
            "action_type": "solo_activity",
            "action_detail": "プログラミングをしている",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.SOLO_ACTIVITY
        assert result.action_detail == "プログラミングをしている"

    @pytest.mark.asyncio
    async def test_solo_activity_logs(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "読書しよう",
            "action_type": "solo_activity",
            "action_detail": "読書をしている",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        assert "[アイネ] 読書をしている" in content


class TestThinkCycleStartConversation:
    """Tests for ThinkCycle returning START_CONVERSATION action."""

    @pytest.mark.asyncio
    async def test_start_conversation(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "クロエに話しかけよう",
            "action_type": "start_conversation",
            "action_detail": "挨拶する",
            "target_character_id": "chloe",
        })

        chars = {
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
        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state(characters=chars)

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.START_CONVERSATION
        assert result.target_character_id == "chloe"

    @pytest.mark.asyncio
    async def test_start_conversation_logs(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "クロエに話しかけよう",
            "action_type": "start_conversation",
            "action_detail": "挨拶する",
            "target_character_id": "chloe",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        assert "[アイネ]" in content


class TestThinkCycleUseTool:
    """Tests for ThinkCycle returning USE_TOOL action."""

    @pytest.mark.asyncio
    async def test_use_tool(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "ブログを書きたい",
            "action_type": "use_tool",
            "action_detail": "ブログ記事を執筆",
            "tool_name": "blog_write",
            "tool_input": "今日の出来事について",
        })

        registry = ToolRegistry()
        tool = ToolDefinition(
            name="blog_write",
            description="ブログ記事を書く",
            model="sonnet",
        )

        async def blog_handler(input: str, llm: object) -> str:
            return "ブログ記事: 今日は良い天気でした"

        registry.register(tool, blog_handler)

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=registry,
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.USE_TOOL
        assert result.tool_name == "blog_write"

    @pytest.mark.asyncio
    async def test_use_tool_executes_handler(self, tmp_path: Path) -> None:
        """Tool handler should be called during the act phase."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "メモを書こう",
            "action_type": "use_tool",
            "action_detail": "メモを作成",
            "tool_name": "note_write",
            "tool_input": "買い物リスト",
        })

        registry = ToolRegistry()
        tool = ToolDefinition(
            name="note_write",
            description="メモを書く",
            model="haiku",
        )
        handler_calls: list[str] = []

        async def note_handler(input: str, llm: object) -> str:
            handler_calls.append(input)
            return f"メモ作成完了: {input}"

        registry.register(tool, note_handler)

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=registry,
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        assert handler_calls == ["買い物リスト"]


class TestThinkCycleMarkdownParsing:
    """Tests for handling LLM responses wrapped in markdown code blocks."""

    @pytest.mark.asyncio
    async def test_parse_markdown_wrapped_json(self, tmp_path: Path) -> None:
        """Haiku sometimes wraps JSON in ```json ... ``` blocks."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response_with_markdown({
            "thought": "何もしない",
            "action_type": "idle",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.IDLE
        assert result.thought == "何もしない"


class TestThinkCycleInvalidJSON:
    """Tests for graceful fallback when LLM returns unparseable response."""

    @pytest.mark.asyncio
    async def test_unparseable_response_returns_idle(self, tmp_path: Path) -> None:
        """When LLM returns invalid JSON, ThinkCycle should return IDLE with fallback thought."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = LLMResponse(
            content="I'm sorry, I can't generate valid JSON right now.",
            model="claude-haiku-4-5-20251001",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.IDLE
        assert result.thought != ""  # Should have a fallback thought, not empty

    @pytest.mark.asyncio
    async def test_truncated_json_returns_idle(self, tmp_path: Path) -> None:
        """When LLM returns truncated JSON, ThinkCycle should return IDLE."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = LLMResponse(
            content='{"thought": "考え中", "action_type":',
            model="claude-haiku-4-5-20251001",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.IDLE
        assert result.thought != ""

    @pytest.mark.asyncio
    async def test_invalid_action_type_returns_idle(self, tmp_path: Path) -> None:
        """When LLM returns an unknown action_type, ThinkCycle should return IDLE."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "何かしよう",
            "action_type": "fly_to_moon",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        result = await cycle.execute("aine", "アイネ", world_state)

        assert result.action_type == ActionType.IDLE
        assert result.thought != ""


class TestThinkCycleLLMInteraction:
    """Tests for ThinkCycle's interaction with the LLM."""

    @pytest.mark.asyncio
    async def test_calls_llm_generate(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "テスト",
            "action_type": "idle",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_request_contains_character_context(self, tmp_path: Path) -> None:
        """LLM request should contain character situation info."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "テスト",
            "action_type": "idle",
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
        # System prompt should reference the character
        assert "アイネ" in request.system_prompt or "アイネ" in str(request.messages)

    @pytest.mark.asyncio
    async def test_does_not_mutate_world_state(self, tmp_path: Path) -> None:
        """ThinkCycle should NOT modify WorldState directly."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "移動しよう",
            "action_type": "move",
            "action_detail": "廊下へ",
            "target_location": "hallway",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
        )
        world_state = _make_world_state()
        original_location = world_state.characters["aine"].location
        original_activity = world_state.characters["aine"].activity

        await cycle.execute("aine", "アイネ", world_state)

        # WorldState should be unchanged
        assert world_state.characters["aine"].location == original_location
        assert world_state.characters["aine"].activity == original_activity

    @pytest.mark.asyncio
    async def test_uses_think_model(self, tmp_path: Path) -> None:
        """ThinkCycle should use the configured think model."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = _make_llm_response({
            "thought": "テスト",
            "action_type": "idle",
        })

        world_log = WorldLog(log_dir=tmp_path)
        cycle = ThinkCycle(
            llm=mock_llm,
            tool_registry=ToolRegistry(),
            world_log=world_log,
            think_model="test-model",
        )
        world_state = _make_world_state()

        await cycle.execute("aine", "アイネ", world_state)

        call_args = mock_llm.generate.call_args
        request = call_args[0][0] if call_args[0] else call_args[1].get("request")
        assert request.model == "test-model"

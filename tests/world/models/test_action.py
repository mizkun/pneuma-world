"""Tests for ActionType and ThinkResult models."""

from __future__ import annotations

from pneuma_world.models.action import ActionType, ThinkResult


class TestActionType:
    """Tests for ActionType enum."""

    def test_idle_value(self) -> None:
        assert ActionType.IDLE.value == "idle"

    def test_move_value(self) -> None:
        assert ActionType.MOVE.value == "move"

    def test_solo_activity_value(self) -> None:
        assert ActionType.SOLO_ACTIVITY.value == "solo_activity"

    def test_start_conversation_value(self) -> None:
        assert ActionType.START_CONVERSATION.value == "start_conversation"

    def test_use_tool_value(self) -> None:
        assert ActionType.USE_TOOL.value == "use_tool"

    def test_all_members(self) -> None:
        members = {m.value for m in ActionType}
        assert members == {
            "idle",
            "move",
            "solo_activity",
            "start_conversation",
            "use_tool",
        }

    def test_from_string(self) -> None:
        assert ActionType("idle") is ActionType.IDLE
        assert ActionType("move") is ActionType.MOVE


class TestThinkResult:
    """Tests for ThinkResult dataclass."""

    def test_minimal_creation(self) -> None:
        result = ThinkResult(
            thought="何もすることがない",
            action_type=ActionType.IDLE,
        )
        assert result.thought == "何もすることがない"
        assert result.action_type == ActionType.IDLE
        assert result.action_detail is None
        assert result.tool_name is None
        assert result.tool_input is None
        assert result.target_character_id is None
        assert result.target_location is None

    def test_move_action(self) -> None:
        result = ThinkResult(
            thought="部室に行こう",
            action_type=ActionType.MOVE,
            action_detail="部室に向かう",
            target_location="clubroom",
        )
        assert result.action_type == ActionType.MOVE
        assert result.target_location == "clubroom"
        assert result.action_detail == "部室に向かう"

    def test_solo_activity(self) -> None:
        result = ThinkResult(
            thought="コードを書こう",
            action_type=ActionType.SOLO_ACTIVITY,
            action_detail="プログラミングをしている",
        )
        assert result.action_type == ActionType.SOLO_ACTIVITY
        assert result.action_detail == "プログラミングをしている"

    def test_start_conversation(self) -> None:
        result = ThinkResult(
            thought="アイネに話しかけよう",
            action_type=ActionType.START_CONVERSATION,
            action_detail="挨拶する",
            target_character_id="aine",
        )
        assert result.action_type == ActionType.START_CONVERSATION
        assert result.target_character_id == "aine"

    def test_use_tool(self) -> None:
        result = ThinkResult(
            thought="ブログを書きたい",
            action_type=ActionType.USE_TOOL,
            action_detail="ブログ記事を執筆",
            tool_name="blog_write",
            tool_input="今日の出来事について書く",
        )
        assert result.action_type == ActionType.USE_TOOL
        assert result.tool_name == "blog_write"
        assert result.tool_input == "今日の出来事について書く"

    def test_all_fields(self) -> None:
        result = ThinkResult(
            thought="thought",
            action_type=ActionType.USE_TOOL,
            action_detail="detail",
            tool_name="blog_write",
            tool_input="input",
            target_character_id="char1",
            target_location="loc1",
        )
        assert result.thought == "thought"
        assert result.action_type == ActionType.USE_TOOL
        assert result.action_detail == "detail"
        assert result.tool_name == "blog_write"
        assert result.tool_input == "input"
        assert result.target_character_id == "char1"
        assert result.target_location == "loc1"

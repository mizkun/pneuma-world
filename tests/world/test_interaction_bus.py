"""Tests for InteractionBus: character-to-character conversation mediator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pneuma_core.models.emotion import EmotionalState
from pneuma_core.models.message import MessageInput, MessageOutput
from pneuma_world.interaction_bus import InteractionBus
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, Conversation, WorldState
from pneuma_world.world_log import WorldLog

JST = timezone(timedelta(hours=9))

# --- Helpers ---


def _make_emotion() -> EmotionalState:
    return EmotionalState(
        pleasure=0.5,
        arousal=0.3,
        dominance=0.2,
        emotion_label="happy",
        situation="talking",
    )


def _make_message_output(
    speech: str,
    thought: str | None = None,
    action: str | None = None,
) -> MessageOutput:
    """Create a MessageOutput with structured response fields."""
    return MessageOutput(
        content=speech,
        emotion=_make_emotion(),
        thought=thought,
        action=action,
    )


def _make_world_state(
    *,
    characters: dict[str, CharacterState] | None = None,
) -> WorldState:
    """Create a minimal WorldState for testing."""
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


def _make_engines(
    aine_responses: list[MessageOutput] | None = None,
    chloe_responses: list[MessageOutput] | None = None,
) -> dict[str, AsyncMock]:
    """Create mock RuntimeEngines for aine and chloe."""
    aine_engine = AsyncMock()
    chloe_engine = AsyncMock()

    if aine_responses:
        aine_engine.process_message.side_effect = aine_responses
    else:
        aine_engine.process_message.return_value = _make_message_output("うん、そうだね")

    if chloe_responses:
        chloe_engine.process_message.side_effect = chloe_responses
    else:
        chloe_engine.process_message.return_value = _make_message_output("おはよう！")

    return {"aine": aine_engine, "chloe": chloe_engine}


def _make_character_names() -> dict[str, str]:
    return {"aine": "アイネ", "chloe": "クロエ"}


# --- InteractionBus Tests ---


class TestStartConversation:
    """Tests for InteractionBus.start_conversation."""

    @pytest.mark.asyncio
    async def test_returns_conversation_object(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="おはよう！",
            world_state=world_state,
        )

        assert isinstance(conversation, Conversation)
        assert "aine" in conversation.participant_ids
        assert "chloe" in conversation.participant_ids
        assert conversation.location == "clubroom"

    @pytest.mark.asyncio
    async def test_conversation_has_unique_id(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conv1 = await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="おはよう！",
            world_state=world_state,
        )
        conv2 = await bus.start_conversation(
            initiator_id="chloe",
            target_id="aine",
            opening_message="こんにちは！",
            world_state=world_state,
        )

        assert conv1.id != conv2.id

    @pytest.mark.asyncio
    async def test_sends_opening_message_to_target(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="おはよう！",
            world_state=world_state,
        )

        # The target's engine should have been called with the opening message
        engines["chloe"].process_message.assert_called_once()
        call_args = engines["chloe"].process_message.call_args[0][0]
        assert isinstance(call_args, MessageInput)
        assert call_args.content == "おはよう！"
        assert call_args.sender_id == "aine"
        assert call_args.sender_name == "アイネ"
        assert call_args.sender_type == "character"

    @pytest.mark.asyncio
    async def test_logs_opening_speech(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="おはよう！",
            world_state=world_state,
        )

        log_file = tmp_path / "2026-03-01.md"
        assert log_file.exists()
        content = log_file.read_text()
        assert "[アイネ] 「おはよう！」" in content


class TestContinueConversation:
    """Tests for InteractionBus.continue_conversation."""

    @pytest.mark.asyncio
    async def test_sends_message_via_target_engine(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        # aine speaks, so chloe's engine processes it
        result = await bus.continue_conversation(
            conversation=conversation,
            speaker_id="aine",
            message="今日は天気がいいね",
            world_state=world_state,
        )

        engines["chloe"].process_message.assert_called_once()
        call_args = engines["chloe"].process_message.call_args[0][0]
        assert call_args.sender_id == "aine"
        assert call_args.sender_type == "character"
        assert call_args.content == "今日は天気がいいね"

    @pytest.mark.asyncio
    async def test_returns_message_output(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.continue_conversation(
            conversation=conversation,
            speaker_id="aine",
            message="今日は天気がいいね",
            world_state=world_state,
        )

        assert isinstance(result, MessageOutput)

    @pytest.mark.asyncio
    async def test_logs_speech(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        await bus.continue_conversation(
            conversation=conversation,
            speaker_id="aine",
            message="今日は天気がいいね",
            world_state=world_state,
        )

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        # Should log the speaker's message
        assert "[アイネ] 「今日は天気がいいね」" in content

    @pytest.mark.asyncio
    async def test_reverse_direction(self, tmp_path: Path) -> None:
        """When chloe speaks, aine's engine should process it."""
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        await bus.continue_conversation(
            conversation=conversation,
            speaker_id="chloe",
            message="今日の予定は？",
            world_state=world_state,
        )

        engines["aine"].process_message.assert_called_once()
        call_args = engines["aine"].process_message.call_args[0][0]
        assert call_args.sender_id == "chloe"
        assert call_args.sender_name == "クロエ"


class TestRunConversation:
    """Tests for InteractionBus.run_conversation (full conversation loop)."""

    @pytest.mark.asyncio
    async def test_returns_list_of_speech_tuples(self, tmp_path: Path) -> None:
        """run_conversation returns list of (character_id, speech) tuples."""
        aine_responses = [
            _make_message_output("そうだね、いい天気だ"),
            _make_message_output("じゃあ散歩でもしようか"),
        ]
        chloe_responses = [
            _make_message_output("おはよう、アイネ！"),
            _make_message_output("いいね、行こう！"),
        ]
        engines = _make_engines(
            aine_responses=aine_responses,
            chloe_responses=chloe_responses,
        )
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="おはよう！",
            world_state=world_state,
            max_turns=4,
        )

        assert isinstance(result, list)
        assert len(result) > 0
        # Each entry is (character_id, speech)
        for char_id, speech in result:
            assert isinstance(char_id, str)
            assert isinstance(speech, str)

    @pytest.mark.asyncio
    async def test_opening_message_is_first(self, tmp_path: Path) -> None:
        """The initiator's opening message should be first in the result."""
        chloe_responses = [_make_message_output("おはよう！")]
        engines = _make_engines(chloe_responses=chloe_responses)
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="やっほー！",
            world_state=world_state,
            max_turns=2,
        )

        # First entry is the initiator's opening
        assert result[0] == ("aine", "やっほー！")

    @pytest.mark.asyncio
    async def test_respects_max_turns(self, tmp_path: Path) -> None:
        """Conversation should not exceed max_turns."""
        # Provide enough responses for many turns
        aine_responses = [_make_message_output(f"aine-{i}") for i in range(10)]
        chloe_responses = [_make_message_output(f"chloe-{i}") for i in range(10)]
        engines = _make_engines(
            aine_responses=aine_responses,
            chloe_responses=chloe_responses,
        )
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="hi",
            world_state=world_state,
            max_turns=4,
        )

        assert len(result) <= 4

    @pytest.mark.asyncio
    async def test_alternates_speakers(self, tmp_path: Path) -> None:
        """Conversation should alternate between initiator and target."""
        aine_responses = [_make_message_output(f"aine-{i}") for i in range(5)]
        chloe_responses = [_make_message_output(f"chloe-{i}") for i in range(5)]
        engines = _make_engines(
            aine_responses=aine_responses,
            chloe_responses=chloe_responses,
        )
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="start",
            world_state=world_state,
            max_turns=6,
        )

        # Should alternate: aine, chloe, aine, chloe, ...
        for i, (char_id, _) in enumerate(result):
            if i % 2 == 0:
                assert char_id == "aine", f"Turn {i} should be aine"
            else:
                assert char_id == "chloe", f"Turn {i} should be chloe"

    @pytest.mark.asyncio
    async def test_logs_all_speech_to_world_log(self, tmp_path: Path) -> None:
        """All speech during conversation should be logged to WorldLog."""
        chloe_responses = [_make_message_output("こんにちは！")]
        engines = _make_engines(chloe_responses=chloe_responses)
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        await bus.run_conversation(
            conversation=conversation,
            opening_message="おはよう！",
            world_state=world_state,
            max_turns=2,
        )

        log_file = tmp_path / "2026-03-01.md"
        content = log_file.read_text()
        assert "[アイネ] 「おはよう！」" in content
        assert "[クロエ] 「こんにちは！」" in content

    @pytest.mark.asyncio
    async def test_default_max_turns_is_8(self, tmp_path: Path) -> None:
        """Default max_turns should be 8."""
        aine_responses = [_make_message_output(f"aine-{i}") for i in range(10)]
        chloe_responses = [_make_message_output(f"chloe-{i}") for i in range(10)]
        engines = _make_engines(
            aine_responses=aine_responses,
            chloe_responses=chloe_responses,
        )
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="hi",
            world_state=world_state,
        )

        assert len(result) <= 8


class TestShouldEndConversation:
    """Tests for InteractionBus.should_end_conversation."""

    def test_ends_at_max_turns(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )

        response = _make_message_output("普通の応答")
        assert bus.should_end_conversation(response, turn=8, max_turns=8) is True

    def test_does_not_end_before_max_turns(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )

        response = _make_message_output("普通の応答")
        assert bus.should_end_conversation(response, turn=3, max_turns=8) is False

    def test_ends_on_farewell_keyword(self, tmp_path: Path) -> None:
        """Should end when response contains farewell signals."""
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )

        response = _make_message_output("じゃあね、またね！")
        assert bus.should_end_conversation(response, turn=3, max_turns=8) is True

    def test_ends_on_bye(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )

        response = _make_message_output("バイバイ！")
        assert bus.should_end_conversation(response, turn=2, max_turns=8) is True

    def test_ends_on_sayonara(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )

        response = _make_message_output("さようなら")
        assert bus.should_end_conversation(response, turn=2, max_turns=8) is True

    def test_no_end_on_regular_speech(self, tmp_path: Path) -> None:
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )

        response = _make_message_output("今日はいい天気だね")
        assert bus.should_end_conversation(response, turn=2, max_turns=8) is False

    def test_ends_on_farewell_action(self, tmp_path: Path) -> None:
        """Should end when action field indicates farewell."""
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )

        response = _make_message_output(
            "それじゃ",
            action="手を振って去る",
        )
        assert bus.should_end_conversation(response, turn=2, max_turns=8) is True


class TestRunConversationEndDetection:
    """Tests for run_conversation ending via should_end_conversation."""

    @pytest.mark.asyncio
    async def test_ends_early_on_farewell(self, tmp_path: Path) -> None:
        """Conversation should end early if a farewell keyword is detected."""
        chloe_responses = [
            _make_message_output("じゃあね、またね！"),
        ]
        engines = _make_engines(chloe_responses=chloe_responses)
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-1",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="おはよう！",
            world_state=world_state,
            max_turns=8,
        )

        # Should end after: aine opens + chloe says farewell = 2 turns
        assert len(result) == 2
        assert result[1][1] == "じゃあね、またね！"

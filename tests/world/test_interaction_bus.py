"""Tests for InteractionBus: character-to-character conversation mediator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


# --- Helpers for multi-person tests ---


def _make_three_person_world_state() -> WorldState:
    """Create a WorldState with 3 characters in the same room."""
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
        "mira": CharacterState(
            character_id="mira",
            location="clubroom",
            position=Position(120, 150),
            activity="idle",
        ),
    }
    return WorldState(
        tick=1,
        world_time=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
        characters=chars,
        active_conversations=[],
        locations={
            "clubroom": Location(
                id="clubroom",
                name="部室",
                bounds=(Position(0, 0), Position(200, 200)),
            ),
        },
    )


def _make_three_person_engines(
    aine_responses: list[MessageOutput] | None = None,
    chloe_responses: list[MessageOutput] | None = None,
    mira_responses: list[MessageOutput] | None = None,
) -> dict[str, AsyncMock]:
    """Create mock RuntimeEngines for aine, chloe, and mira."""
    aine_engine = AsyncMock()
    chloe_engine = AsyncMock()
    mira_engine = AsyncMock()

    if aine_responses:
        aine_engine.process_message.side_effect = aine_responses
    else:
        aine_engine.process_message.return_value = _make_message_output("うん、そうだね")

    if chloe_responses:
        chloe_engine.process_message.side_effect = chloe_responses
    else:
        chloe_engine.process_message.return_value = _make_message_output("おはよう！")

    if mira_responses:
        mira_engine.process_message.side_effect = mira_responses
    else:
        mira_engine.process_message.return_value = _make_message_output("私もそう思う")

    return {"aine": aine_engine, "chloe": chloe_engine, "mira": mira_engine}


def _make_three_person_names() -> dict[str, str]:
    return {"aine": "アイネ", "chloe": "クロエ", "mira": "ミラ"}


def _make_mock_llm_adapter(responses: list[str] | None = None) -> AsyncMock:
    """Create a mock LLMAdapter for willingness checks.

    Each response should be 'yes' or 'no'.
    """
    from pneuma_core.llm.adapter import LLMResponse

    adapter = AsyncMock()
    if responses:
        adapter.generate.side_effect = [
            LLMResponse(content=r, model="haiku", usage={}) for r in responses
        ]
    else:
        adapter.generate.return_value = LLMResponse(
            content="yes", model="haiku", usage={}
        )
    return adapter


# --- Multi-Person Conversation Tests ---


class TestMultiPersonConversation:
    """Tests for 3+ person conversation with willingness check."""

    @pytest.mark.asyncio
    async def test_three_person_willingness_check_is_called(
        self, tmp_path: Path
    ) -> None:
        """3人会話で発言意思判定が行われることを確認。"""
        # LLM adapter: both chloe and mira want to speak
        llm = _make_mock_llm_adapter(["yes", "yes"])

        engines = _make_three_person_engines(
            chloe_responses=[_make_message_output("そうだね！")],
            mira_responses=[_make_message_output("私もそう思う！")],
        )
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_three_person_names(),
            llm=llm,
        )

        conversation = Conversation(
            id="conv-multi-1",
            participant_ids=["aine", "chloe", "mira"],
            started_at=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
            location="clubroom",
        )
        world_state = _make_three_person_world_state()

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="みんなおはよう！",
            world_state=world_state,
            max_turns=3,
        )

        # Opening + at least one response from willingness-checked speaker
        assert len(result) >= 2
        # LLM adapter should have been called for willingness checks
        assert llm.generate.call_count >= 1

    @pytest.mark.asyncio
    async def test_all_decline_ends_conversation(self, tmp_path: Path) -> None:
        """全員が「発言しない」で会話が終了することを確認。"""
        # LLM adapter: both chloe and mira say "no"
        llm = _make_mock_llm_adapter(["no", "no"])

        engines = _make_three_person_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_three_person_names(),
            llm=llm,
        )

        conversation = Conversation(
            id="conv-multi-2",
            participant_ids=["aine", "chloe", "mira"],
            started_at=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
            location="clubroom",
        )
        world_state = _make_three_person_world_state()

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="みんなおはよう！",
            world_state=world_state,
            max_turns=8,
        )

        # Only the opening message, then nobody wanted to speak
        assert len(result) == 1
        assert result[0] == ("aine", "みんなおはよう！")

    @pytest.mark.asyncio
    async def test_two_person_uses_alternating_mode(self, tmp_path: Path) -> None:
        """2人の会話は従来通り交互発言で動作することを確認。"""
        aine_responses = [_make_message_output("aine-reply")]
        chloe_responses = [_make_message_output("chloe-reply")]
        engines = _make_engines(
            aine_responses=aine_responses,
            chloe_responses=chloe_responses,
        )
        world_log = WorldLog(log_dir=tmp_path)
        # llm=None: 2人会話ではLLMアダプタ不要
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
        )
        world_state = _make_world_state()

        conversation = Conversation(
            id="conv-2p",
            participant_ids=["aine", "chloe"],
            started_at=world_state.world_time,
            location="clubroom",
        )

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="やっほー",
            world_state=world_state,
            max_turns=3,
        )

        # Should alternate: aine, chloe, aine
        assert result[0] == ("aine", "やっほー")
        assert result[1][0] == "chloe"
        assert result[2][0] == "aine"

    @pytest.mark.asyncio
    async def test_willingness_check_runs_in_parallel(
        self, tmp_path: Path
    ) -> None:
        """発言意思判定が asyncio.gather で並列実行されることを確認。"""
        import asyncio

        call_order: list[str] = []
        original_gather = asyncio.gather

        # Track that asyncio.gather is used for willingness checks
        gather_called = False

        async def tracking_gather(*coros, **kwargs):
            nonlocal gather_called
            gather_called = True
            return await original_gather(*coros, **kwargs)

        # Both say yes, first speaker (chloe) responds
        llm = _make_mock_llm_adapter(["yes", "yes"])
        engines = _make_three_person_engines(
            chloe_responses=[_make_message_output("はい！")],
            mira_responses=[_make_message_output("うん！")],
        )
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_three_person_names(),
            llm=llm,
        )

        conversation = Conversation(
            id="conv-parallel",
            participant_ids=["aine", "chloe", "mira"],
            started_at=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
            location="clubroom",
        )
        world_state = _make_three_person_world_state()

        with patch("pneuma_world.interaction_bus.asyncio.gather", side_effect=tracking_gather):
            result = await bus.run_conversation(
                conversation=conversation,
                opening_message="テスト",
                world_state=world_state,
                max_turns=2,
            )

        assert gather_called, "asyncio.gather should be used for parallel willingness checks"


class TestConversationFrequencyGovernor:
    """Tests for conversation frequency governor."""

    @pytest.mark.asyncio
    async def test_rejects_conversation_over_hourly_limit(
        self, tmp_path: Path
    ) -> None:
        """1時間以内の会話開始回数が上限を超えた場合、start_conversation を却下。"""
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
            max_conversations_per_hour=2,
        )
        world_state = _make_world_state()

        # Start 2 conversations (within limit)
        for i in range(2):
            conv = await bus.start_conversation(
                initiator_id="aine",
                target_id="chloe",
                opening_message=f"会話{i}",
                world_state=world_state,
            )
            assert conv is not None

        # 3rd conversation should be rejected
        result = await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="もう一回",
            world_state=world_state,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_conversation_after_hour_passes(
        self, tmp_path: Path
    ) -> None:
        """1時間経過後は再び会話を開始できることを確認。"""
        engines = _make_engines()
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_character_names(),
            max_conversations_per_hour=1,
        )
        world_state = _make_world_state()

        # 1st conversation at 10:30
        conv = await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="おはよう",
            world_state=world_state,
        )
        assert conv is not None

        # 2nd at 10:30 -> rejected
        result = await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="もう一回",
            world_state=world_state,
        )
        assert result is None

        # Advance world time by 61 minutes -> allowed
        later_state = _make_world_state()
        later_state.world_time = world_state.world_time + timedelta(minutes=61)
        result = await bus.start_conversation(
            initiator_id="aine",
            target_id="chloe",
            opening_message="こんにちは",
            world_state=later_state,
        )
        assert result is not None


class TestMultiPersonSpeakerSelection:
    """Tests for speaker selection logic in multi-person conversations."""

    @pytest.mark.asyncio
    async def test_addressed_person_gets_priority(self, tmp_path: Path) -> None:
        """直前に話しかけられた人が発言優先されることを確認。"""
        # Both want to speak, but opening mentions chloe by name
        llm = _make_mock_llm_adapter(["yes", "yes"])
        engines = _make_three_person_engines(
            chloe_responses=[_make_message_output("はい、なに？")],
            mira_responses=[_make_message_output("うん")],
        )
        world_log = WorldLog(log_dir=tmp_path)
        bus = InteractionBus(
            engines=engines,
            world_log=world_log,
            character_names=_make_three_person_names(),
            llm=llm,
        )

        conversation = Conversation(
            id="conv-priority",
            participant_ids=["aine", "chloe", "mira"],
            started_at=datetime(2026, 3, 1, 10, 30, 0, tzinfo=JST),
            location="clubroom",
        )
        world_state = _make_three_person_world_state()

        result = await bus.run_conversation(
            conversation=conversation,
            opening_message="クロエ、これ見て！",
            world_state=world_state,
            max_turns=2,
        )

        # Second speaker should be chloe (addressed by name)
        assert len(result) >= 2
        assert result[1][0] == "chloe"

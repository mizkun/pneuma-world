"""InteractionBus: mediates conversations between characters."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pneuma_core.models.message import MessageInput, MessageOutput
from pneuma_world.models.state import Conversation, WorldState
from pneuma_world.world_log import WorldLog

if TYPE_CHECKING:
    from pneuma_core.runtime.engine import RuntimeEngine

# Farewell keywords that signal end of conversation
_FAREWELL_KEYWORDS = frozenset({
    "じゃあね",
    "またね",
    "バイバイ",
    "さようなら",
    "お先に",
    "失礼します",
})

# Action keywords that signal farewell
_FAREWELL_ACTION_KEYWORDS = frozenset({
    "去る",
    "立ち去る",
    "離れる",
    "帰る",
})


class InteractionBus:
    """Mediates conversations between characters using RuntimeEngine.

    InteractionBus does NOT modify WorldState directly. It returns conversation
    data, and the caller (WorldEngine) applies changes to WorldState.
    """

    def __init__(
        self,
        engines: dict[str, RuntimeEngine],
        world_log: WorldLog,
        character_names: dict[str, str],
    ) -> None:
        self._engines = engines
        self._world_log = world_log
        self._character_names = character_names

    async def start_conversation(
        self,
        initiator_id: str,
        target_id: str,
        opening_message: str,
        world_state: WorldState,
    ) -> Conversation:
        """Start a new conversation between two characters.

        Creates a Conversation object, logs the opening message,
        and sends the first message to the target's RuntimeEngine.
        """
        # Create conversation
        initiator_state = world_state.characters[initiator_id]
        conversation = Conversation(
            id=str(uuid.uuid4()),
            participant_ids=[initiator_id, target_id],
            started_at=world_state.world_time,
            location=initiator_state.location,
        )

        # Log the opening speech
        initiator_name = self._character_names.get(initiator_id, initiator_id)
        self._world_log.record_speech(
            initiator_name, opening_message, world_state.world_time
        )

        # Send opening message to target's engine
        target_engine = self._engines[target_id]
        msg = MessageInput(
            content=opening_message,
            sender_id=initiator_id,
            sender_name=initiator_name,
            sender_type="character",
            channel="world",
        )
        await target_engine.process_message(msg)

        return conversation

    async def continue_conversation(
        self,
        conversation: Conversation,
        speaker_id: str,
        message: str,
        world_state: WorldState,
    ) -> MessageOutput:
        """Continue an existing conversation.

        Sends message through the listener's RuntimeEngine with
        sender_type='character'.
        """
        # Determine the listener (the other participant)
        listener_id = next(
            pid for pid in conversation.participant_ids if pid != speaker_id
        )

        # Log the speaker's message
        speaker_name = self._character_names.get(speaker_id, speaker_id)
        self._world_log.record_speech(
            speaker_name, message, world_state.world_time
        )

        # Send through listener's engine
        listener_engine = self._engines[listener_id]
        msg = MessageInput(
            content=message,
            sender_id=speaker_id,
            sender_name=speaker_name,
            sender_type="character",
            channel="world",
        )
        return await listener_engine.process_message(msg)

    async def run_conversation(
        self,
        conversation: Conversation,
        opening_message: str,
        world_state: WorldState,
        max_turns: int = 8,
    ) -> list[tuple[str, str]]:
        """Run a full conversation loop.

        Flow:
        1. Initiator sends opening message (logged)
        2. Target responds via RuntimeEngine
        3. Initiator responds to target's response
        4. Repeat until max_turns or conversation naturally ends

        Returns list of (character_id, speech) tuples.
        """
        initiator_id = conversation.participant_ids[0]
        target_id = conversation.participant_ids[1]

        transcript: list[tuple[str, str]] = []
        turn = 0

        # Turn 1: initiator's opening message
        transcript.append((initiator_id, opening_message))
        initiator_name = self._character_names.get(initiator_id, initiator_id)
        self._world_log.record_speech(
            initiator_name, opening_message, world_state.world_time
        )
        turn += 1

        if turn >= max_turns:
            return transcript

        # Turn 2: target responds to opening
        target_engine = self._engines[target_id]
        msg = MessageInput(
            content=opening_message,
            sender_id=initiator_id,
            sender_name=initiator_name,
            sender_type="character",
            channel="world",
        )
        response = await target_engine.process_message(msg)
        response_speech = response.content
        transcript.append((target_id, response_speech))

        target_name = self._character_names.get(target_id, target_id)
        self._world_log.record_speech(
            target_name, response_speech, world_state.world_time
        )
        turn += 1

        if self.should_end_conversation(response, turn, max_turns):
            return transcript

        # Continue alternating
        current_speaker_id = initiator_id
        current_listener_id = target_id
        last_speech = response_speech

        while turn < max_turns:
            # current_speaker responds to last_speech
            speaker_engine = self._engines[current_speaker_id]
            listener_name = self._character_names.get(
                current_listener_id, current_listener_id
            )
            speaker_name = self._character_names.get(
                current_speaker_id, current_speaker_id
            )

            msg = MessageInput(
                content=last_speech,
                sender_id=current_listener_id,
                sender_name=listener_name,
                sender_type="character",
                channel="world",
            )
            response = await speaker_engine.process_message(msg)
            response_speech = response.content
            transcript.append((current_speaker_id, response_speech))

            self._world_log.record_speech(
                speaker_name, response_speech, world_state.world_time
            )
            turn += 1

            if self.should_end_conversation(response, turn, max_turns):
                break

            # Swap roles
            last_speech = response_speech
            current_speaker_id, current_listener_id = (
                current_listener_id,
                current_speaker_id,
            )

        return transcript

    def should_end_conversation(
        self, response: MessageOutput, turn: int, max_turns: int
    ) -> bool:
        """Determine if conversation should end.

        - Max turns reached
        - Response contains farewell signals
        """
        if turn >= max_turns:
            return True

        # Check speech content for farewell keywords
        speech = response.content or ""
        for keyword in _FAREWELL_KEYWORDS:
            if keyword in speech:
                return True

        # Check action field for farewell signals
        action = response.action or ""
        for keyword in _FAREWELL_ACTION_KEYWORDS:
            if keyword in action:
                return True

        return False

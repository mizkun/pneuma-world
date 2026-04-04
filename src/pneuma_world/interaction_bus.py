"""InteractionBus: mediates conversations between characters."""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pneuma_core.models.message import MessageInput, MessageOutput
from pneuma_world.models.state import Conversation, WorldState
from pneuma_world.world_log import WorldLog

if TYPE_CHECKING:
    from pneuma_core.llm.adapter import LLMAdapter
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

# Default max conversations per hour per initiator
_DEFAULT_MAX_CONVERSATIONS_PER_HOUR = 10

# Willingness check prompt template
_WILLINGNESS_PROMPT = (
    "以下の会話を聞いて、あなたは発言したいですか？ yes/no で答えてください。\n\n"
    "直前の発言: {last_speech}\n"
    "発言者: {speaker_name}"
)


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
        llm: LLMAdapter | None = None,
        max_conversations_per_hour: int = _DEFAULT_MAX_CONVERSATIONS_PER_HOUR,
    ) -> None:
        self._engines = engines
        self._world_log = world_log
        self._character_names = character_names
        self._llm = llm
        self._max_conversations_per_hour = max_conversations_per_hour
        # Frequency governor: initiator_id -> list of conversation start times
        self._conversation_counts: dict[str, list[datetime]] = {}

    def _check_frequency_limit(
        self, initiator_id: str, current_time: datetime
    ) -> bool:
        """Check if the initiator has exceeded the hourly conversation limit.

        Returns True if allowed, False if over limit.
        """
        times = self._conversation_counts.get(initiator_id, [])
        one_hour_ago = current_time - timedelta(hours=1)
        # Filter to only recent conversations
        recent = [t for t in times if t > one_hour_ago]
        self._conversation_counts[initiator_id] = recent
        return len(recent) < self._max_conversations_per_hour

    def _record_conversation_start(
        self, initiator_id: str, current_time: datetime
    ) -> None:
        """Record a conversation start for frequency tracking."""
        if initiator_id not in self._conversation_counts:
            self._conversation_counts[initiator_id] = []
        self._conversation_counts[initiator_id].append(current_time)

    async def start_conversation(
        self,
        initiator_id: str,
        target_id: str,
        opening_message: str,
        world_state: WorldState,
    ) -> Conversation | None:
        """Start a new conversation between two characters.

        Creates a Conversation object, logs the opening message,
        and sends the first message to the target's RuntimeEngine.

        Returns None if the frequency governor rejects the conversation.
        """
        # Frequency governor check
        if not self._check_frequency_limit(initiator_id, world_state.world_time):
            return None

        # Record this conversation start
        self._record_conversation_start(initiator_id, world_state.world_time)

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

        Automatically dispatches to two-person or multi-person mode
        based on participant count.
        """
        if len(conversation.participant_ids) <= 2:
            return await self._run_two_person(
                conversation, opening_message, world_state, max_turns
            )
        else:
            return await self._run_multi_person(
                conversation, opening_message, world_state, max_turns
            )

    async def _run_two_person(
        self,
        conversation: Conversation,
        opening_message: str,
        world_state: WorldState,
        max_turns: int = 8,
    ) -> list[tuple[str, str]]:
        """Run a full two-person conversation loop (original behavior).

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

    async def _run_multi_person(
        self,
        conversation: Conversation,
        opening_message: str,
        world_state: WorldState,
        max_turns: int = 8,
    ) -> list[tuple[str, str]]:
        """Run a multi-person conversation (3+ participants).

        Algorithm:
        1. Initiator sends opening message
        2. All other participants are asked (in parallel) if they want to speak
        3. If multiple want to speak, pick one (addressed person priority, else random)
        4. Chosen person speaks via RuntimeEngine
        5. If nobody wants to speak, conversation ends
        6. Repeat until max_turns
        """
        initiator_id = conversation.participant_ids[0]

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

        last_speaker_id = initiator_id
        last_speech = opening_message

        while turn < max_turns:
            # Determine candidates (everyone except last speaker)
            candidates = [
                pid
                for pid in conversation.participant_ids
                if pid != last_speaker_id
            ]

            # Check willingness in parallel
            willing = await self._check_willingness_parallel(
                candidates, last_speech, last_speaker_id
            )

            if not willing:
                # Nobody wants to speak -> end conversation
                break

            # Select speaker
            next_speaker_id = self._select_speaker(
                willing, last_speech
            )

            # Next speaker responds
            speaker_engine = self._engines[next_speaker_id]
            speaker_name = self._character_names.get(
                next_speaker_id, next_speaker_id
            )
            last_speaker_name = self._character_names.get(
                last_speaker_id, last_speaker_id
            )

            msg = MessageInput(
                content=last_speech,
                sender_id=last_speaker_id,
                sender_name=last_speaker_name,
                sender_type="character",
                channel="world",
            )
            response = await speaker_engine.process_message(msg)
            response_speech = response.content
            transcript.append((next_speaker_id, response_speech))

            self._world_log.record_speech(
                speaker_name, response_speech, world_state.world_time
            )
            turn += 1

            if self.should_end_conversation(response, turn, max_turns):
                break

            last_speaker_id = next_speaker_id
            last_speech = response_speech

        return transcript

    async def _check_willingness_parallel(
        self,
        candidate_ids: list[str],
        last_speech: str,
        last_speaker_id: str,
    ) -> list[str]:
        """Check willingness to speak for all candidates in parallel.

        Returns list of candidate IDs who want to speak.
        """
        if not self._llm:
            return []

        from pneuma_core.llm.adapter import LLMRequest

        last_speaker_name = self._character_names.get(
            last_speaker_id, last_speaker_id
        )

        async def check_one(candidate_id: str) -> str | None:
            prompt = _WILLINGNESS_PROMPT.format(
                last_speech=last_speech,
                speaker_name=last_speaker_name,
            )
            candidate_name = self._character_names.get(
                candidate_id, candidate_id
            )
            request = LLMRequest(
                system_prompt=f"あなたは「{candidate_name}」です。",
                messages=[{"role": "user", "content": prompt}],
                model="claude-haiku-4-5-20251001",
                temperature=0.3,
                max_tokens=10,
            )
            response = await self._llm.generate(request)
            content = response.content.strip().lower()
            if "yes" in content:
                return candidate_id
            return None

        results = await asyncio.gather(
            *(check_one(cid) for cid in candidate_ids)
        )
        return [r for r in results if r is not None]

    def _select_speaker(
        self,
        willing_ids: list[str],
        last_speech: str,
    ) -> str:
        """Select next speaker from willing candidates.

        Priority: person addressed by name in last_speech, else random.
        """
        if len(willing_ids) == 1:
            return willing_ids[0]

        # Check if any willing candidate was addressed by name
        for candidate_id in willing_ids:
            candidate_name = self._character_names.get(candidate_id, "")
            if candidate_name and candidate_name in last_speech:
                return candidate_id

        # Random selection
        return random.choice(willing_ids)

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

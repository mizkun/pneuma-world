"""WorldEngine: the top-level orchestrator for the World Engine."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from pneuma_world.clock import WorldClock, interpolate_position
from pneuma_world.models.action import ActionType, ThinkResult
from pneuma_world.models.location import Position
from pneuma_world.models.state import CharacterState, Conversation, WorldState
from pneuma_world.world_log import WorldLog

if TYPE_CHECKING:
    from pneuma_world.interaction_bus import InteractionBus
    from pneuma_world.think_cycle import ThinkCycle


class WorldEngine:
    """Top-level orchestrator that ties WorldClock, ThinkCycle,
    InteractionBus, and WorldLog together.

    Owns and mutates WorldState. Each tick():
    1. Advance WorldClock
    2. Update visual positions (interpolate for moving characters)
    3. If think tick fires:
       a. Run ThinkCycle for each character (not in conversation)
       b. Apply ThinkResults to WorldState
       c. Handle START_CONVERSATION via InteractionBus
    4. Return list of ThinkResults (empty if no think tick)
    """

    def __init__(
        self,
        world_state: WorldState,
        clock: WorldClock,
        think_cycle: ThinkCycle,
        interaction_bus: InteractionBus,
        world_log: WorldLog,
        character_names: dict[str, str],
    ) -> None:
        self._world_state = world_state
        self._clock = clock
        self._think_cycle = think_cycle
        self._interaction_bus = interaction_bus
        self._world_log = world_log
        self._character_names = character_names

    @property
    def state(self) -> WorldState:
        """Current world state."""
        return self._world_state

    async def tick(self) -> list[ThinkResult]:
        """Execute one visual tick.

        Returns:
            List of ThinkResults if a think tick fired, empty list otherwise.
        """
        # 1. Advance clock
        is_think_tick = self._clock.advance_visual_tick()

        # 2. Update visual positions for all moving characters
        self._update_positions()

        # 3. Advance world_time
        think_interval = self._clock._config.think_interval_seconds
        visual_interval = self._clock._config.visual_interval_seconds
        self._world_state.world_time += timedelta(seconds=visual_interval)

        if not is_think_tick:
            return []

        # 4. Think tick: run ThinkCycle for eligible characters
        self._world_state.tick += 1
        results: list[ThinkResult] = []

        for char_id, char_state in self._world_state.characters.items():
            # Skip characters in conversation
            if char_state.conversation_id is not None:
                continue

            char_name = self._character_names.get(char_id, char_id)
            result = await self._think_cycle.execute(
                char_id, char_name, self._world_state
            )
            results.append(result)

            # Apply result to world state
            self.apply_think_result(char_id, result)

        # Handle START_CONVERSATION actions via InteractionBus
        for result in results:
            if (
                result.action_type != ActionType.START_CONVERSATION
                or result.target_character_id is None
            ):
                continue

            # Find the conversation matching this result's target
            conv = self._find_conversation_for(result.target_character_id)
            if conv is None:
                continue

            opening = result.action_detail or "こんにちは"
            try:
                await self._interaction_bus.run_conversation(
                    conversation=conv,
                    opening_message=opening,
                    world_state=self._world_state,
                )
            except Exception:
                pass  # Log error in future; ensure cleanup always runs
            finally:
                # Cleanup: reset participants' state so they are eligible
                # for future think ticks
                for participant_id in conv.participant_ids:
                    participant = self._world_state.characters.get(participant_id)
                    if participant is not None:
                        participant.conversation_id = None
                        participant.activity = "idle"
                if conv in self._world_state.active_conversations:
                    self._world_state.active_conversations.remove(conv)

        return results

    def apply_think_result(self, character_id: str, result: ThinkResult) -> None:
        """Apply a ThinkResult to WorldState.

        - IDLE: no change
        - MOVE: set target_position, change activity to 'walking'
        - SOLO_ACTIVITY: change activity
        - START_CONVERSATION: create Conversation, set both characters to 'talking'
        - USE_TOOL: change activity
        """
        char = self._world_state.characters.get(character_id)
        if char is None:
            return

        if result.action_type == ActionType.IDLE:
            pass  # No change

        elif result.action_type == ActionType.MOVE:
            # Set target position based on target_location
            if result.target_location:
                location = self._world_state.locations.get(result.target_location)
                if location:
                    # Move toward the center of the target location
                    center_x = (location.bounds[0].x + location.bounds[1].x) // 2
                    center_y = (location.bounds[0].y + location.bounds[1].y) // 2
                    char.target_position = Position(x=center_x, y=center_y)
                    char.location = result.target_location
            char.activity = "walking"

        elif result.action_type == ActionType.SOLO_ACTIVITY:
            char.activity = result.action_detail or "活動中"

        elif result.action_type == ActionType.START_CONVERSATION:
            target_id = result.target_character_id
            if target_id and target_id in self._world_state.characters:
                target_char = self._world_state.characters[target_id]
                conv_id = str(uuid.uuid4())

                conv = Conversation(
                    id=conv_id,
                    participant_ids=[character_id, target_id],
                    started_at=self._world_state.world_time,
                    location=char.location,
                )
                self._world_state.active_conversations.append(conv)

                char.activity = "talking"
                char.conversation_id = conv_id
                target_char.activity = "talking"
                target_char.conversation_id = conv_id

        elif result.action_type == ActionType.USE_TOOL:
            char.activity = result.action_detail or f"ツール使用中: {result.tool_name}"

    def _find_conversation_for(self, target_character_id: str) -> Conversation | None:
        """Find the active conversation that includes target_character_id."""
        for conv in self._world_state.active_conversations:
            if target_character_id in conv.participant_ids:
                return conv
        return None

    def _update_positions(self) -> None:
        """Update positions for all characters with target_position."""
        for char_id, char_state in self._world_state.characters.items():
            if char_state.target_position is not None:
                new_pos = interpolate_position(
                    char_state.position,
                    char_state.target_position,
                )
                char_state.position = new_pos

                # Clear target if reached
                if new_pos == char_state.target_position:
                    char_state.target_position = None

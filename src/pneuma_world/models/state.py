"""CharacterState, Conversation, and WorldState models for the World Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pneuma_world.models.location import Location, Position


@dataclass
class CharacterState:
    """Runtime state of a character in the world.

    Attributes:
        character_id: Reference to Character.id.
        location: Location.id where the character currently is.
        position: Current pixel position on the map.
        activity: Current activity label (e.g. "idle", "reading", "talking").
        target_position: Destination position during movement, or None.
        conversation_id: Active Conversation.id if the character is talking.
    """

    character_id: str
    location: str
    position: Position
    activity: str
    target_position: Position | None = None
    conversation_id: str | None = None


@dataclass
class Conversation:
    """An active conversation between characters.

    Attributes:
        id: Unique conversation identifier.
        participant_ids: List of Character.id values involved.
        started_at: When the conversation began.
        location: Location.id where the conversation takes place.
    """

    id: str
    participant_ids: list[str]
    started_at: datetime
    location: str


@dataclass
class WorldState:
    """Complete snapshot of the world at a given tick.

    Attributes:
        tick: Current think-tick number.
        world_time: In-world datetime.
        characters: Mapping of character_id to CharacterState.
        active_conversations: List of ongoing Conversations.
        locations: Mapping of location_id to Location.
    """

    tick: int
    world_time: datetime
    characters: dict[str, CharacterState]
    active_conversations: list[Conversation]
    locations: dict[str, Location]

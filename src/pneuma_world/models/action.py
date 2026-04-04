"""ActionType and ThinkResult models for World Engine think cycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ActionType(Enum):
    """Types of actions a character can decide to take."""

    IDLE = "idle"
    MOVE = "move"
    SOLO_ACTIVITY = "solo_activity"
    START_CONVERSATION = "start_conversation"
    USE_TOOL = "use_tool"


@dataclass
class MiniAction:
    """A single action step within an action queue.

    Attributes:
        action: Action type ("walk_to", "interact", "sit", "idle_animation").
        target: POI id or furniture id (empty string if not applicable).
        animation: Animation name (empty string if not applicable).
        duration: Duration in seconds.
    """

    action: str
    target: str
    animation: str
    duration: int


@dataclass
class ThinkResult:
    """Result of a single think cycle for a character.

    Attributes:
        thought: Internal monologue (what the character is thinking).
        action_type: The decided action type.
        action_detail: Description of the action (e.g., target location, activity).
        tool_name: Tool to use (if USE_TOOL).
        tool_input: Input for the tool (if USE_TOOL).
        target_character_id: Who to talk to (if START_CONVERSATION).
        target_location: Where to go (if MOVE).
    """

    thought: str
    action_type: ActionType
    action_detail: str | None = None
    tool_name: str | None = None
    tool_input: str | None = None
    target_character_id: str | None = None
    target_location: str | None = None
    action_queue: list[MiniAction] = field(default_factory=list)

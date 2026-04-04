"""WorldEvent model for the intervention interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class WorldEvent:
    """An event that can be injected into the world.

    Attributes:
        type: Event category - "environment" | "character_contact" | "scenario" | "physical"
        content: Human-readable event description (e.g. "雨が降ってきた")
        source: Origin of the event - "human" | "orchestrator" | "random_table"
        target: Target scope - "world" (all characters) or a specific character_id
        timestamp: When the event was created
        id: Unique event identifier
    """

    type: str  # "environment" | "character_contact" | "scenario" | "physical"
    content: str  # "雨が降ってきた" etc.
    source: str  # "human" | "orchestrator" | "random_table"
    target: str  # "world" | specific_character_id
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

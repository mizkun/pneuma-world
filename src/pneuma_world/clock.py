"""WorldClock: 2-layer tick system and position interpolation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pneuma_world.models.location import Position


@dataclass
class TickConfig:
    """Configuration for the 2-layer tick system.

    Attributes:
        visual_interval_seconds: Seconds per visual tick (default 1.0).
        think_interval_seconds: Seconds per think tick (default 900.0 = 15 min).
    """

    visual_interval_seconds: float = 1.0
    think_interval_seconds: float = 900.0


class WorldClock:
    """2-layer tick clock for the World Engine.

    Visual ticks drive animation/movement at a fast rate.
    Think ticks drive AI reasoning at a slower rate.
    """

    def __init__(self, config: TickConfig | None = None) -> None:
        self._config = config or TickConfig()
        self._visual_ticks: int = 0
        self._think_ticks: int = 0

    @property
    def tick_count(self) -> int:
        """Number of think ticks that have occurred."""
        return self._think_ticks

    @property
    def visual_tick_count(self) -> int:
        """Number of visual ticks that have occurred."""
        return self._visual_ticks

    def advance_visual_tick(self) -> bool:
        """Advance one visual tick.

        Returns:
            True if a think tick also fires on this visual tick.
        """
        self._visual_ticks += 1
        elapsed_seconds = self._visual_ticks * self._config.visual_interval_seconds
        expected_think_ticks = int(elapsed_seconds / self._config.think_interval_seconds)
        if expected_think_ticks > self._think_ticks:
            self._think_ticks = expected_think_ticks
            return True
        return False

    def should_think(self) -> bool:
        """Check if the current visual tick count has reached a think tick boundary."""
        elapsed_seconds = self._visual_ticks * self._config.visual_interval_seconds
        expected_think_ticks = int(elapsed_seconds / self._config.think_interval_seconds)
        return expected_think_ticks > 0 and expected_think_ticks >= self._think_ticks

    def get_elapsed_think_ticks(self) -> int:
        """Number of think ticks that have occurred."""
        return self._think_ticks


def interpolate_position(
    current: Position,
    target: Position,
    speed: float = 1.0,
) -> Position:
    """Move current position toward target by speed pixels per visual tick.

    Args:
        current: Current position.
        target: Target position to move toward.
        speed: Pixels to move per visual tick.

    Returns:
        New Position after moving. Snaps to target if close enough.
    """
    dx = target.x - current.x
    dy = target.y - current.y
    distance = math.hypot(dx, dy)

    if distance <= speed:
        return target

    # Normalize direction and scale by speed
    ratio = speed / distance
    new_x = current.x + round(dx * ratio)
    new_y = current.y + round(dy * ratio)
    return Position(x=new_x, y=new_y)

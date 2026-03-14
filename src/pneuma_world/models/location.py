"""Location and Position models for the World Engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Position:
    """An immutable 2D position on the world map."""

    x: int
    y: int


@dataclass
class Location:
    """A named area in the world with defined bounds.

    Attributes:
        id: Unique identifier (e.g. "clubroom", "hallway").
        name: Human-readable display name.
        bounds: Tuple of (top-left, bottom-right) Position defining the area.
        walkable_area: Optional list of walkable sub-rectangles within the location.
    """

    id: str
    name: str
    bounds: tuple[Position, Position]
    walkable_area: list[tuple[Position, Position]] | None = None

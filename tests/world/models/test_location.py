"""Tests for Location and Position models."""

from __future__ import annotations

import pytest

from pneuma_world.models.location import Location, Position


class TestPosition:
    """Tests for Position value object."""

    def test_create_position(self) -> None:
        pos = Position(x=10, y=20)
        assert pos.x == 10
        assert pos.y == 20

    def test_position_is_frozen(self) -> None:
        pos = Position(x=10, y=20)
        with pytest.raises(AttributeError):
            pos.x = 30  # type: ignore[misc]

    def test_position_equality(self) -> None:
        a = Position(x=5, y=10)
        b = Position(x=5, y=10)
        assert a == b

    def test_position_inequality(self) -> None:
        a = Position(x=5, y=10)
        b = Position(x=5, y=11)
        assert a != b

    def test_position_hashable(self) -> None:
        """Frozen dataclass should be hashable (usable in sets/dicts)."""
        a = Position(x=1, y=2)
        b = Position(x=1, y=2)
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_position_zero(self) -> None:
        pos = Position(x=0, y=0)
        assert pos.x == 0
        assert pos.y == 0

    def test_position_negative(self) -> None:
        pos = Position(x=-5, y=-10)
        assert pos.x == -5
        assert pos.y == -10


class TestLocation:
    """Tests for Location model."""

    def test_create_location(self) -> None:
        loc = Location(
            id="clubroom",
            name="Club Room",
            bounds=(Position(0, 0), Position(100, 80)),
        )
        assert loc.id == "clubroom"
        assert loc.name == "Club Room"
        assert loc.bounds == (Position(0, 0), Position(100, 80))
        assert loc.walkable_area is None

    def test_location_with_walkable_area(self) -> None:
        walkable = [
            (Position(10, 10), Position(50, 50)),
            (Position(60, 10), Position(90, 50)),
        ]
        loc = Location(
            id="hallway",
            name="Hallway",
            bounds=(Position(0, 0), Position(200, 50)),
            walkable_area=walkable,
        )
        assert loc.walkable_area is not None
        assert len(loc.walkable_area) == 2

    def test_location_default_walkable_is_none(self) -> None:
        loc = Location(
            id="room",
            name="Room",
            bounds=(Position(0, 0), Position(50, 50)),
        )
        assert loc.walkable_area is None

    def test_location_bounds_are_position_tuples(self) -> None:
        top_left = Position(0, 0)
        bottom_right = Position(100, 100)
        loc = Location(
            id="room",
            name="Room",
            bounds=(top_left, bottom_right),
        )
        assert loc.bounds[0] == top_left
        assert loc.bounds[1] == bottom_right

    def test_location_is_mutable(self) -> None:
        """Location is a regular (non-frozen) dataclass."""
        loc = Location(
            id="room",
            name="Room",
            bounds=(Position(0, 0), Position(50, 50)),
        )
        loc.name = "Updated Room"
        assert loc.name == "Updated Room"

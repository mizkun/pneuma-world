"""Tests for WorldClock and position interpolation."""

from __future__ import annotations

import math

from pneuma_world.clock import WorldClock, TickConfig, interpolate_position
from pneuma_world.models.location import Position


class TestTickConfig:
    """Tests for TickConfig defaults and customization."""

    def test_default_config(self) -> None:
        config = TickConfig()
        assert config.visual_interval_seconds == 1.0
        assert config.think_interval_seconds == 900.0

    def test_custom_config(self) -> None:
        config = TickConfig(
            visual_interval_seconds=0.5,
            think_interval_seconds=60.0,
        )
        assert config.visual_interval_seconds == 0.5
        assert config.think_interval_seconds == 60.0


class TestWorldClock:
    """Tests for WorldClock tick system."""

    def test_initial_state(self) -> None:
        clock = WorldClock()
        assert clock.tick_count == 0
        assert clock.visual_tick_count == 0

    def test_initial_state_with_config(self) -> None:
        config = TickConfig(visual_interval_seconds=2.0, think_interval_seconds=10.0)
        clock = WorldClock(config=config)
        assert clock.tick_count == 0
        assert clock.visual_tick_count == 0

    def test_advance_visual_tick(self) -> None:
        clock = WorldClock()
        result = clock.advance_visual_tick()
        assert clock.visual_tick_count == 1
        # First tick should not trigger think tick (with default 900s interval)
        assert result is False

    def test_advance_multiple_visual_ticks(self) -> None:
        clock = WorldClock()
        for _ in range(10):
            clock.advance_visual_tick()
        assert clock.visual_tick_count == 10

    def test_think_tick_fires_at_interval(self) -> None:
        """Think tick should fire when enough visual ticks accumulate."""
        config = TickConfig(
            visual_interval_seconds=1.0,
            think_interval_seconds=5.0,
        )
        clock = WorldClock(config=config)

        # Advance 4 visual ticks (4 seconds) — no think tick yet
        for _ in range(4):
            result = clock.advance_visual_tick()
            assert result is False

        # 5th tick should trigger think tick (5 seconds elapsed)
        result = clock.advance_visual_tick()
        assert result is True
        assert clock.get_elapsed_think_ticks() == 1

    def test_think_tick_fires_periodically(self) -> None:
        """Think tick should fire every N visual ticks."""
        config = TickConfig(
            visual_interval_seconds=1.0,
            think_interval_seconds=3.0,
        )
        clock = WorldClock(config=config)

        think_fires = []
        for i in range(12):
            result = clock.advance_visual_tick()
            if result:
                think_fires.append(i + 1)  # 1-based tick number

        # Should fire at ticks 3, 6, 9, 12
        assert think_fires == [3, 6, 9, 12]
        assert clock.get_elapsed_think_ticks() == 4

    def test_should_think_initially_false(self) -> None:
        clock = WorldClock()
        assert clock.should_think() is False

    def test_should_think_after_interval(self) -> None:
        config = TickConfig(
            visual_interval_seconds=1.0,
            think_interval_seconds=3.0,
        )
        clock = WorldClock(config=config)

        for _ in range(2):
            clock.advance_visual_tick()
        assert clock.should_think() is False

        clock.advance_visual_tick()
        assert clock.should_think() is True

    def test_tick_count_is_think_ticks(self) -> None:
        """tick_count should track think ticks."""
        config = TickConfig(
            visual_interval_seconds=1.0,
            think_interval_seconds=5.0,
        )
        clock = WorldClock(config=config)

        for _ in range(5):
            clock.advance_visual_tick()
        assert clock.tick_count == 1

        for _ in range(5):
            clock.advance_visual_tick()
        assert clock.tick_count == 2

    def test_elapsed_think_ticks_matches_tick_count(self) -> None:
        config = TickConfig(
            visual_interval_seconds=1.0,
            think_interval_seconds=2.0,
        )
        clock = WorldClock(config=config)

        for _ in range(6):
            clock.advance_visual_tick()

        assert clock.tick_count == clock.get_elapsed_think_ticks()
        assert clock.tick_count == 3

    def test_fractional_interval_ratio(self) -> None:
        """Handle non-integer ratio of think/visual intervals."""
        config = TickConfig(
            visual_interval_seconds=0.5,
            think_interval_seconds=1.5,
        )
        clock = WorldClock(config=config)

        # 1.5 / 0.5 = 3 visual ticks per think tick
        results = []
        for _ in range(6):
            results.append(clock.advance_visual_tick())

        # Think ticks at visual ticks 3 and 6
        assert results == [False, False, True, False, False, True]
        assert clock.tick_count == 2


class TestInterpolatePosition:
    """Tests for position interpolation."""

    def test_no_movement_when_at_target(self) -> None:
        current = Position(50, 50)
        target = Position(50, 50)
        result = interpolate_position(current, target, speed=1.0)
        assert result == Position(50, 50)

    def test_move_right(self) -> None:
        current = Position(0, 0)
        target = Position(10, 0)
        result = interpolate_position(current, target, speed=3.0)
        assert result == Position(3, 0)

    def test_move_left(self) -> None:
        current = Position(10, 0)
        target = Position(0, 0)
        result = interpolate_position(current, target, speed=3.0)
        assert result == Position(7, 0)

    def test_move_up(self) -> None:
        current = Position(0, 10)
        target = Position(0, 0)
        result = interpolate_position(current, target, speed=3.0)
        assert result == Position(0, 7)

    def test_move_down(self) -> None:
        current = Position(0, 0)
        target = Position(0, 10)
        result = interpolate_position(current, target, speed=3.0)
        assert result == Position(0, 3)

    def test_move_diagonal(self) -> None:
        current = Position(0, 0)
        target = Position(10, 10)
        result = interpolate_position(current, target, speed=1.0)
        # Distance is sqrt(200) ~= 14.14
        # Direction is (10/14.14, 10/14.14) ~= (0.707, 0.707)
        # Movement: (0.707, 0.707) * 1.0 -> rounded to (1, 1)
        assert result == Position(1, 1)

    def test_snap_to_target_when_close(self) -> None:
        """Should snap to target when distance <= speed."""
        current = Position(9, 9)
        target = Position(10, 10)
        # Distance is sqrt(2) ~= 1.41
        result = interpolate_position(current, target, speed=2.0)
        assert result == Position(10, 10)

    def test_snap_to_target_exact_distance(self) -> None:
        """Should snap when distance exactly equals speed."""
        current = Position(0, 0)
        target = Position(3, 4)
        # Distance is exactly 5.0
        result = interpolate_position(current, target, speed=5.0)
        assert result == Position(3, 4)

    def test_default_speed_is_one(self) -> None:
        current = Position(0, 0)
        target = Position(10, 0)
        result = interpolate_position(current, target)
        assert result == Position(1, 0)

    def test_large_speed(self) -> None:
        """Large speed should snap to target (overshoot prevention)."""
        current = Position(0, 0)
        target = Position(5, 5)
        result = interpolate_position(current, target, speed=100.0)
        assert result == Position(5, 5)

    def test_movement_preserves_integer_positions(self) -> None:
        """Positions use int coordinates; interpolation should round."""
        current = Position(0, 0)
        target = Position(7, 3)
        result = interpolate_position(current, target, speed=2.0)
        assert isinstance(result.x, int)
        assert isinstance(result.y, int)

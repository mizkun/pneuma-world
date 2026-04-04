"""Tests for intervention interface and random event table (#5)."""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from pneuma_world.models.event import WorldEvent
from pneuma_world.events import EventQueue, RandomEventTable


class TestWorldEvent:
    """WorldEvent dataclass tests."""

    def test_create_world_event_with_required_fields(self) -> None:
        event = WorldEvent(
            type="environment",
            content="雨が降ってきた",
            source="human",
            target="world",
        )
        assert event.type == "environment"
        assert event.content == "雨が降ってきた"
        assert event.source == "human"
        assert event.target == "world"

    def test_world_event_has_auto_generated_id(self) -> None:
        event = WorldEvent(
            type="environment",
            content="test",
            source="human",
            target="world",
        )
        assert event.id is not None
        assert len(event.id) > 0

    def test_world_event_has_auto_generated_timestamp(self) -> None:
        before = datetime.now()
        event = WorldEvent(
            type="environment",
            content="test",
            source="human",
            target="world",
        )
        after = datetime.now()
        assert before <= event.timestamp <= after

    def test_world_event_ids_are_unique(self) -> None:
        e1 = WorldEvent(type="environment", content="a", source="human", target="world")
        e2 = WorldEvent(type="environment", content="b", source="human", target="world")
        assert e1.id != e2.id

    def test_world_event_type_values(self) -> None:
        for event_type in ("environment", "character_contact", "scenario", "physical"):
            event = WorldEvent(
                type=event_type,
                content="test",
                source="human",
                target="world",
            )
            assert event.type == event_type

    def test_world_event_source_values(self) -> None:
        for source in ("human", "orchestrator", "random_table"):
            event = WorldEvent(
                type="environment",
                content="test",
                source=source,
                target="world",
            )
            assert event.source == source


class TestEventQueue:
    """EventQueue push/drain tests."""

    @pytest.fixture
    def queue(self) -> EventQueue:
        return EventQueue()

    async def test_push_and_drain_single_event(self, queue: EventQueue) -> None:
        event = WorldEvent(
            type="environment",
            content="雨が降ってきた",
            source="human",
            target="world",
        )
        await queue.push(event)
        events = queue.drain()
        assert len(events) == 1
        assert events[0] is event

    async def test_push_and_drain_multiple_events(self, queue: EventQueue) -> None:
        e1 = WorldEvent(type="environment", content="a", source="human", target="world")
        e2 = WorldEvent(type="physical", content="b", source="orchestrator", target="world")
        e3 = WorldEvent(type="scenario", content="c", source="random_table", target="char1")
        await queue.push(e1)
        await queue.push(e2)
        await queue.push(e3)
        events = queue.drain()
        assert len(events) == 3
        assert events[0] is e1
        assert events[1] is e2
        assert events[2] is e3

    async def test_drain_empty_queue_returns_empty_list(self, queue: EventQueue) -> None:
        events = queue.drain()
        assert events == []

    async def test_drain_clears_queue(self, queue: EventQueue) -> None:
        event = WorldEvent(type="environment", content="a", source="human", target="world")
        await queue.push(event)
        queue.drain()
        events = queue.drain()
        assert events == []

    async def test_push_after_drain(self, queue: EventQueue) -> None:
        e1 = WorldEvent(type="environment", content="a", source="human", target="world")
        await queue.push(e1)
        queue.drain()

        e2 = WorldEvent(type="physical", content="b", source="human", target="world")
        await queue.push(e2)
        events = queue.drain()
        assert len(events) == 1
        assert events[0] is e2


class TestRandomEventTable:
    """RandomEventTable YAML loading and weighted selection tests."""

    @pytest.fixture
    def events_yaml_path(self, tmp_path) -> str:
        data = {
            "events": [
                {"type": "environment", "content": "窓の外で猫が鳴いている", "weight": 3},
                {"type": "environment", "content": "チャイムが鳴った", "weight": 2},
                {"type": "physical", "content": "棚から本が1冊落ちた", "weight": 1},
            ]
        }
        path = tmp_path / "events.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f, allow_unicode=True)
        return str(path)

    def test_load_from_yaml(self, events_yaml_path: str) -> None:
        table = RandomEventTable.from_yaml(events_yaml_path)
        assert len(table.entries) == 3

    def test_entries_have_correct_types(self, events_yaml_path: str) -> None:
        table = RandomEventTable.from_yaml(events_yaml_path)
        types = [e["type"] for e in table.entries]
        assert "environment" in types
        assert "physical" in types

    def test_entries_have_weights(self, events_yaml_path: str) -> None:
        table = RandomEventTable.from_yaml(events_yaml_path)
        weights = [e["weight"] for e in table.entries]
        assert weights == [3, 2, 1]

    def test_roll_returns_world_event(self, events_yaml_path: str) -> None:
        table = RandomEventTable.from_yaml(events_yaml_path)
        event = table.roll()
        assert isinstance(event, WorldEvent)
        assert event.source == "random_table"
        assert event.target == "world"

    def test_roll_respects_weights(self, events_yaml_path: str) -> None:
        """Higher weight events should appear more frequently."""
        table = RandomEventTable.from_yaml(events_yaml_path)
        counts: dict[str, int] = {}
        n = 6000
        for _ in range(n):
            event = table.roll()
            counts[event.content] = counts.get(event.content, 0) + 1

        # weight 3 should be ~3x weight 1
        assert counts["窓の外で猫が鳴いている"] > counts["棚から本が1冊落ちた"]
        # weight 2 should be ~2x weight 1
        assert counts["チャイムが鳴った"] > counts["棚から本が1冊落ちた"]

    def test_roll_event_has_valid_fields(self, events_yaml_path: str) -> None:
        table = RandomEventTable.from_yaml(events_yaml_path)
        event = table.roll()
        assert event.type in ("environment", "physical")
        assert len(event.content) > 0
        assert event.id is not None

    def test_load_empty_events_yaml(self, tmp_path) -> None:
        data = {"events": []}
        path = tmp_path / "empty.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)
        table = RandomEventTable.from_yaml(str(path))
        assert len(table.entries) == 0

    def test_roll_on_empty_table_returns_none(self, tmp_path) -> None:
        data = {"events": []}
        path = tmp_path / "empty.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)
        table = RandomEventTable.from_yaml(str(path))
        result = table.roll()
        assert result is None


class TestBuildSituationContextWithEvents:
    """Test _build_situation_context integrates pending events."""

    def test_events_injected_into_situation_context(self) -> None:
        from pneuma_world.think_cycle import _build_situation_context
        from pneuma_world.models.state import WorldState, CharacterState
        from pneuma_world.models.location import Location, Position

        world_state = WorldState(
            tick=1,
            world_time=datetime(2025, 1, 1, 12, 0),
            characters={
                "char1": CharacterState(
                    character_id="char1",
                    location="room1",
                    position=Position(x=0, y=0),
                    activity="idle",
                ),
            },
            active_conversations=[],
            locations={
                "room1": Location(id="room1", name="部屋1", walkable_polygon=[]),
            },
        )

        events = [
            WorldEvent(type="environment", content="雨が降ってきた", source="human", target="world"),
        ]
        context = _build_situation_context(
            "char1", "テストキャラ", world_state, pending_events=events,
        )
        assert "雨が降ってきた" in context

    def test_targeted_event_only_for_specific_character(self) -> None:
        from pneuma_world.think_cycle import _build_situation_context
        from pneuma_world.models.state import WorldState, CharacterState
        from pneuma_world.models.location import Location, Position

        world_state = WorldState(
            tick=1,
            world_time=datetime(2025, 1, 1, 12, 0),
            characters={
                "char1": CharacterState(
                    character_id="char1",
                    location="room1",
                    position=Position(x=0, y=0),
                    activity="idle",
                ),
                "char2": CharacterState(
                    character_id="char2",
                    location="room1",
                    position=Position(x=10, y=10),
                    activity="reading",
                ),
            },
            active_conversations=[],
            locations={
                "room1": Location(id="room1", name="部屋1", walkable_polygon=[]),
            },
        )

        events = [
            WorldEvent(
                type="character_contact",
                content="誰かに肩を叩かれた",
                source="human",
                target="char1",
            ),
        ]

        # char1 should see the event
        context_char1 = _build_situation_context(
            "char1", "キャラ1", world_state, pending_events=events,
        )
        assert "誰かに肩を叩かれた" in context_char1

        # char2 should NOT see the event targeted at char1
        context_char2 = _build_situation_context(
            "char2", "キャラ2", world_state, pending_events=events,
        )
        assert "誰かに肩を叩かれた" not in context_char2

    def test_world_target_event_visible_to_all(self) -> None:
        from pneuma_world.think_cycle import _build_situation_context
        from pneuma_world.models.state import WorldState, CharacterState
        from pneuma_world.models.location import Location, Position

        world_state = WorldState(
            tick=1,
            world_time=datetime(2025, 1, 1, 12, 0),
            characters={
                "char1": CharacterState(
                    character_id="char1",
                    location="room1",
                    position=Position(x=0, y=0),
                    activity="idle",
                ),
                "char2": CharacterState(
                    character_id="char2",
                    location="room1",
                    position=Position(x=10, y=10),
                    activity="reading",
                ),
            },
            active_conversations=[],
            locations={
                "room1": Location(id="room1", name="部屋1", walkable_polygon=[]),
            },
        )

        events = [
            WorldEvent(
                type="environment",
                content="チャイムが鳴った",
                source="random_table",
                target="world",
            ),
        ]

        context_char1 = _build_situation_context(
            "char1", "キャラ1", world_state, pending_events=events,
        )
        context_char2 = _build_situation_context(
            "char2", "キャラ2", world_state, pending_events=events,
        )
        assert "チャイムが鳴った" in context_char1
        assert "チャイムが鳴った" in context_char2

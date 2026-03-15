"""Tests for CharacterState, Conversation, and WorldState models."""

from __future__ import annotations

from datetime import datetime

from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, Conversation, WorldState


class TestCharacterState:
    """Tests for CharacterState model."""

    def test_create_character_state(self) -> None:
        state = CharacterState(
            character_id="aine",
            location="clubroom",
            position=Position(50, 40),
            activity="idle",
        )
        assert state.character_id == "aine"
        assert state.location == "clubroom"
        assert state.position == Position(50, 40)
        assert state.activity == "idle"
        assert state.target_position is None
        assert state.conversation_id is None

    def test_character_state_with_target(self) -> None:
        state = CharacterState(
            character_id="aine",
            location="clubroom",
            position=Position(10, 10),
            activity="walking",
            target_position=Position(80, 60),
        )
        assert state.target_position == Position(80, 60)

    def test_character_state_with_conversation(self) -> None:
        state = CharacterState(
            character_id="aine",
            location="clubroom",
            position=Position(50, 40),
            activity="talking",
            conversation_id="conv-001",
        )
        assert state.conversation_id == "conv-001"

    def test_character_state_is_mutable(self) -> None:
        state = CharacterState(
            character_id="aine",
            location="clubroom",
            position=Position(50, 40),
            activity="idle",
        )
        state.activity = "reading"
        assert state.activity == "reading"

        state.position = Position(60, 50)
        assert state.position == Position(60, 50)

    def test_character_state_update_location(self) -> None:
        state = CharacterState(
            character_id="aine",
            location="clubroom",
            position=Position(50, 40),
            activity="idle",
        )
        state.location = "hallway"
        assert state.location == "hallway"


class TestConversation:
    """Tests for Conversation model."""

    def test_create_conversation(self) -> None:
        now = datetime(2026, 2, 28, 14, 30, 0)
        conv = Conversation(
            id="conv-001",
            participant_ids=["aine", "chloe"],
            started_at=now,
            location="clubroom",
        )
        assert conv.id == "conv-001"
        assert conv.participant_ids == ["aine", "chloe"]
        assert conv.started_at == now
        assert conv.location == "clubroom"

    def test_conversation_multiple_participants(self) -> None:
        conv = Conversation(
            id="conv-002",
            participant_ids=["aine", "chloe", "mira"],
            started_at=datetime(2026, 2, 28, 15, 0, 0),
            location="hallway",
        )
        assert len(conv.participant_ids) == 3

    def test_conversation_is_mutable(self) -> None:
        conv = Conversation(
            id="conv-001",
            participant_ids=["aine"],
            started_at=datetime(2026, 2, 28, 14, 0, 0),
            location="clubroom",
        )
        conv.participant_ids.append("chloe")
        assert "chloe" in conv.participant_ids


class TestWorldState:
    """Tests for WorldState model."""

    def _make_location(self, id: str = "clubroom", name: str = "Club Room") -> Location:
        return Location(
            id=id,
            name=name,
            bounds=(Position(0, 0), Position(100, 80)),
        )

    def _make_character_state(
        self,
        character_id: str = "aine",
        location: str = "clubroom",
    ) -> CharacterState:
        return CharacterState(
            character_id=character_id,
            location=location,
            position=Position(50, 40),
            activity="idle",
        )

    def test_create_world_state(self) -> None:
        now = datetime(2026, 2, 28, 10, 0, 0)
        loc = self._make_location()
        char = self._make_character_state()

        world = WorldState(
            tick=0,
            world_time=now,
            characters={"aine": char},
            active_conversations=[],
            locations={"clubroom": loc},
        )
        assert world.tick == 0
        assert world.world_time == now
        assert "aine" in world.characters
        assert world.characters["aine"].activity == "idle"
        assert len(world.active_conversations) == 0
        assert "clubroom" in world.locations

    def test_world_state_multiple_characters(self) -> None:
        now = datetime(2026, 2, 28, 10, 0, 0)
        loc = self._make_location()
        aine = self._make_character_state("aine")
        chloe = self._make_character_state("chloe")

        world = WorldState(
            tick=0,
            world_time=now,
            characters={"aine": aine, "chloe": chloe},
            active_conversations=[],
            locations={"clubroom": loc},
        )
        assert len(world.characters) == 2

    def test_world_state_with_conversations(self) -> None:
        now = datetime(2026, 2, 28, 10, 0, 0)
        conv = Conversation(
            id="conv-001",
            participant_ids=["aine", "chloe"],
            started_at=now,
            location="clubroom",
        )

        world = WorldState(
            tick=5,
            world_time=now,
            characters={},
            active_conversations=[conv],
            locations={},
        )
        assert len(world.active_conversations) == 1
        assert world.active_conversations[0].id == "conv-001"

    def test_world_state_is_mutable(self) -> None:
        now = datetime(2026, 2, 28, 10, 0, 0)
        world = WorldState(
            tick=0,
            world_time=now,
            characters={},
            active_conversations=[],
            locations={},
        )
        world.tick = 10
        assert world.tick == 10

    def test_world_state_multiple_locations(self) -> None:
        clubroom = self._make_location("clubroom", "Club Room")
        hallway = self._make_location("hallway", "Hallway")

        world = WorldState(
            tick=0,
            world_time=datetime(2026, 2, 28, 10, 0, 0),
            characters={},
            active_conversations=[],
            locations={"clubroom": clubroom, "hallway": hallway},
        )
        assert len(world.locations) == 2
        assert world.locations["hallway"].name == "Hallway"

    def test_world_state_add_character(self) -> None:
        world = WorldState(
            tick=0,
            world_time=datetime(2026, 2, 28, 10, 0, 0),
            characters={},
            active_conversations=[],
            locations={},
        )
        char = self._make_character_state("aine")
        world.characters["aine"] = char
        assert "aine" in world.characters

    def test_world_state_add_conversation(self) -> None:
        now = datetime(2026, 2, 28, 10, 0, 0)
        world = WorldState(
            tick=0,
            world_time=now,
            characters={},
            active_conversations=[],
            locations={},
        )
        conv = Conversation(
            id="conv-001",
            participant_ids=["aine", "chloe"],
            started_at=now,
            location="clubroom",
        )
        world.active_conversations.append(conv)
        assert len(world.active_conversations) == 1

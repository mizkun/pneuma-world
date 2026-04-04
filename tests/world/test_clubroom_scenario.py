"""Tests for clubroom (kirara-style) scenario: characters, map, events, and ScenarioLoader."""

from pathlib import Path

import pytest
import yaml

from pneuma_core.character_sheet import CharacterSheet
from pneuma_core.models.character import Character
from pneuma_core.models.personality import Personality
from pneuma_core.models.values import Values
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, WorldState
from pneuma_world.scenarios.loader import ScenarioLoader

SCENARIO_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "pneuma_world" / "scenarios" / "clubroom"
CHARACTERS_DIR = SCENARIO_DIR / "characters"
MAP_PATH = SCENARIO_DIR / "map.yaml"
EVENTS_PATH = SCENARIO_DIR / "events.yaml"

# Expected character IDs
CHARACTER_IDS = ["aoi-001", "rin-001", "hinata-001"]


# ---------------------------------------------------------------------------
# Character YAML loading tests
# ---------------------------------------------------------------------------

class TestClubroomCharacterYAMLs:
    """Test that all clubroom character YAML files load via CharacterSheet."""

    @pytest.fixture(params=sorted(CHARACTERS_DIR.glob("*.character.yaml")) if CHARACTERS_DIR.exists() else [])
    def sheet(self, request: pytest.FixtureRequest) -> CharacterSheet:
        """Load each character YAML as a CharacterSheet."""
        return CharacterSheet.load(request.param)

    def test_loads_successfully(self, sheet: CharacterSheet) -> None:
        """Character YAML should load without errors."""
        assert sheet is not None
        assert sheet.character is not None

    def test_character_has_required_fields(self, sheet: CharacterSheet) -> None:
        """Each character must have id, name, personality, values."""
        c = sheet.character
        assert c.id
        assert c.name
        assert isinstance(c.personality, Personality)
        assert isinstance(c.values, Values)

    def test_character_has_profile(self, sheet: CharacterSheet) -> None:
        """Each character should have profile, speaking_style, and background."""
        c = sheet.character
        assert c.profile is not None and len(c.profile) > 0
        assert c.speaking_style is not None and len(c.speaking_style) > 0
        assert c.background is not None and len(c.background) > 0

    def test_has_initial_state(self, sheet: CharacterSheet) -> None:
        """Each character should define an initial emotional state."""
        assert sheet.initial_state is not None

    def test_has_goal_tree(self, sheet: CharacterSheet) -> None:
        """Each character should define goals."""
        assert sheet.goal_tree is not None
        assert len(sheet.goal_tree.visions) >= 1
        assert len(sheet.goal_tree.objectives) >= 1


class TestClubroomPersonalityValues:
    """Test Big Five personality and Schwartz values for clubroom characters."""

    @pytest.fixture
    def sheets(self) -> list[CharacterSheet]:
        return CharacterSheet.load_directory(CHARACTERS_DIR)

    def test_three_characters_loaded(self, sheets: list[CharacterSheet]) -> None:
        """Scenario should have exactly 3 characters."""
        assert len(sheets) == 3

    def test_character_ids(self, sheets: list[CharacterSheet]) -> None:
        """Characters should have expected IDs."""
        ids = {s.character.id for s in sheets}
        assert ids == set(CHARACTER_IDS)

    def test_character_names(self, sheets: list[CharacterSheet]) -> None:
        """Characters should have expected names."""
        names = {s.character.name for s in sheets}
        assert "葵" in " ".join(names) or any("葵" in n for n in names)
        assert "凛" in " ".join(names) or any("凛" in n for n in names)
        assert "ひなた" in " ".join(names) or any("ひなた" in n for n in names)

    def test_personality_values_in_range(self, sheets: list[CharacterSheet]) -> None:
        """All Big Five traits must be between 0.0 and 1.0."""
        traits = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
        for sheet in sheets:
            p = sheet.character.personality
            for trait in traits:
                val = getattr(p, trait)
                assert 0.0 <= val <= 1.0, (
                    f"{sheet.character.name}: {trait} = {val} out of range"
                )

    def test_values_in_range(self, sheets: list[CharacterSheet]) -> None:
        """All Schwartz value dimensions must be between 0.0 and 1.0."""
        dims = ("self_transcendence", "self_enhancement", "openness_to_change", "conservation")
        for sheet in sheets:
            v = sheet.character.values
            for dim in dims:
                val = getattr(v, dim)
                assert 0.0 <= val <= 1.0, (
                    f"{sheet.character.name}: {dim} = {val} out of range"
                )

    def test_aoi_personality_profile(self, sheets: list[CharacterSheet]) -> None:
        """Aoi should be high extraversion (0.85), high openness (0.8), low conscientiousness (0.35)."""
        aoi = next(s for s in sheets if s.character.id == "aoi-001")
        p = aoi.character.personality
        assert p.is_high("extraversion"), f"extraversion={p.extraversion}, expected high"
        assert p.is_high("openness"), f"openness={p.openness}, expected high"
        assert p.is_low("conscientiousness"), f"conscientiousness={p.conscientiousness}, expected low"

    def test_rin_personality_profile(self, sheets: list[CharacterSheet]) -> None:
        """Rin should be high conscientiousness (0.85), low neuroticism (0.2)."""
        rin = next(s for s in sheets if s.character.id == "rin-001")
        p = rin.character.personality
        assert p.is_high("conscientiousness"), f"conscientiousness={p.conscientiousness}, expected high"
        assert p.is_low("neuroticism"), f"neuroticism={p.neuroticism}, expected low"

    def test_hinata_personality_profile(self, sheets: list[CharacterSheet]) -> None:
        """Hinata should be high agreeableness (0.9), high openness (0.75), low extraversion (0.3)."""
        hinata = next(s for s in sheets if s.character.id == "hinata-001")
        p = hinata.character.personality
        assert p.is_high("agreeableness"), f"agreeableness={p.agreeableness}, expected high"
        assert p.is_high("openness"), f"openness={p.openness}, expected high"
        assert p.is_low("extraversion"), f"extraversion={p.extraversion}, expected low"


# ---------------------------------------------------------------------------
# Map YAML tests
# ---------------------------------------------------------------------------

class TestClubroomMapYAML:
    """Test that clubroom map.yaml loads correctly and defines expected locations."""

    @pytest.fixture
    def map_data(self) -> dict:
        text = MAP_PATH.read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def test_map_loads(self, map_data: dict) -> None:
        """map.yaml should parse as a valid dict."""
        assert isinstance(map_data, dict)

    def test_map_has_locations(self, map_data: dict) -> None:
        """Map must define at least one location."""
        assert "locations" in map_data
        assert len(map_data["locations"]) >= 1

    def test_clubroom_location(self, map_data: dict) -> None:
        """The clubroom location should exist with bounds and points_of_interest."""
        clubroom = next(
            (loc for loc in map_data["locations"] if loc["id"] == "clubroom"),
            None,
        )
        assert clubroom is not None
        assert clubroom["name"] == "部室"
        assert "bounds" in clubroom
        assert "points_of_interest" in clubroom

    def test_clubroom_points_of_interest(self, map_data: dict) -> None:
        """Club room should have expected points of interest."""
        clubroom = next(loc for loc in map_data["locations"] if loc["id"] == "clubroom")
        poi_ids = {p["id"] for p in clubroom["points_of_interest"]}
        expected = {"table_center", "chair_1", "chair_2", "chair_3", "bookshelf", "whiteboard", "sofa", "pc", "door"}
        assert expected.issubset(poi_ids), f"Missing POIs: {expected - poi_ids}"

    def test_hallway_location(self, map_data: dict) -> None:
        """Hallway location should exist."""
        hallway = next(
            (loc for loc in map_data["locations"] if loc["id"] == "hallway"),
            None,
        )
        assert hallway is not None
        assert hallway["name"] == "廊下"

    def test_clubroom_bounds(self, map_data: dict) -> None:
        """Clubroom bounds should be [[0,0],[29,29]]."""
        clubroom = next(loc for loc in map_data["locations"] if loc["id"] == "clubroom")
        assert clubroom["bounds"] == [[0, 0], [29, 29]]


# ---------------------------------------------------------------------------
# Events YAML tests
# ---------------------------------------------------------------------------

class TestClubroomEventsYAML:
    """Test that events.yaml loads correctly."""

    @pytest.fixture
    def events_data(self) -> dict:
        text = EVENTS_PATH.read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def test_events_loads(self, events_data: dict) -> None:
        """events.yaml should parse as a valid dict."""
        assert isinstance(events_data, dict)

    def test_events_has_events_key(self, events_data: dict) -> None:
        """Should have an 'events' key with a list."""
        assert "events" in events_data
        assert isinstance(events_data["events"], list)
        assert len(events_data["events"]) >= 1

    def test_events_have_required_fields(self, events_data: dict) -> None:
        """Each event should have type, content, and weight."""
        for event in events_data["events"]:
            assert "type" in event, f"Event missing 'type': {event}"
            assert "content" in event, f"Event missing 'content': {event}"
            assert "weight" in event, f"Event missing 'weight': {event}"

    def test_event_types_are_valid(self, events_data: dict) -> None:
        """Event types should be 'environment' or 'physical'."""
        valid_types = {"environment", "physical"}
        for event in events_data["events"]:
            assert event["type"] in valid_types, f"Invalid type: {event['type']}"

    def test_event_weights_are_positive(self, events_data: dict) -> None:
        """Event weights should be positive integers."""
        for event in events_data["events"]:
            assert isinstance(event["weight"], int) and event["weight"] > 0


# ---------------------------------------------------------------------------
# ScenarioLoader tests
# ---------------------------------------------------------------------------

class TestClubroomScenarioLoader:
    """Test ScenarioLoader creates valid WorldState from clubroom scenario data."""

    @pytest.fixture
    def loader(self) -> ScenarioLoader:
        return ScenarioLoader(SCENARIO_DIR)

    def test_load_characters(self, loader: ScenarioLoader) -> None:
        """Should load 3 Character objects."""
        characters = loader.load_characters()
        assert len(characters) == 3
        for c in characters:
            assert isinstance(c, Character)

    def test_load_characters_ids(self, loader: ScenarioLoader) -> None:
        """Loaded characters should have expected IDs."""
        characters = loader.load_characters()
        ids = {c.id for c in characters}
        assert ids == set(CHARACTER_IDS)

    def test_load_map(self, loader: ScenarioLoader) -> None:
        """Should load map data with locations."""
        map_data = loader.load_map()
        assert "locations" in map_data

    def test_create_initial_world_state(self, loader: ScenarioLoader) -> None:
        """Should create a valid WorldState with all characters and locations."""
        state = loader.create_initial_world_state()
        assert isinstance(state, WorldState)

    def test_world_state_has_all_characters(self, loader: ScenarioLoader) -> None:
        """WorldState should contain CharacterState for each loaded character."""
        state = loader.create_initial_world_state()
        assert len(state.characters) == 3
        for cid in CHARACTER_IDS:
            assert cid in state.characters
            cs = state.characters[cid]
            assert isinstance(cs, CharacterState)

    def test_world_state_has_locations(self, loader: ScenarioLoader) -> None:
        """WorldState should contain Location objects from the map."""
        state = loader.create_initial_world_state()
        assert "clubroom" in state.locations
        assert "hallway" in state.locations
        for loc in state.locations.values():
            assert isinstance(loc, Location)

    def test_world_state_characters_placed_in_clubroom(self, loader: ScenarioLoader) -> None:
        """All characters should be initially placed in the clubroom."""
        state = loader.create_initial_world_state()
        for cs in state.characters.values():
            assert cs.location == "clubroom"
            assert cs.activity == "idle"

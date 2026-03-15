"""Tests for scenario loading: character YAMLs, map, and ScenarioLoader."""

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

SCENARIO_DIR = Path(__file__).resolve().parent.parent.parent / "packages" / "pneuma-world" / "src" / "pneuma_world" / "scenarios" / "yurucamp"
CHARACTERS_DIR = SCENARIO_DIR / "characters"
MAP_PATH = SCENARIO_DIR / "map.yaml"

# Expected character IDs
CHARACTER_IDS = ["nadeshiko-001", "rin-001", "chiaki-001"]


# ---------------------------------------------------------------------------
# Character YAML loading tests
# ---------------------------------------------------------------------------

class TestCharacterYAMLs:
    """Test that all character YAML files load via CharacterSheet."""

    @pytest.fixture(params=sorted(CHARACTERS_DIR.glob("*.character.yaml")))
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


class TestPersonalityValues:
    """Test Big Five personality and Schwartz values are in valid ranges."""

    @pytest.fixture
    def sheets(self) -> list[CharacterSheet]:
        return CharacterSheet.load_directory(CHARACTERS_DIR)

    def test_three_characters_loaded(self, sheets: list[CharacterSheet]) -> None:
        """Scenario should have exactly 3 characters."""
        assert len(sheets) == 3

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

    def test_nadeshiko_personality_profile(self, sheets: list[CharacterSheet]) -> None:
        """Nadeshiko should be high extraversion, high agreeableness, low neuroticism."""
        nadeshiko = next(s for s in sheets if "nadeshiko" in s.character.id)
        p = nadeshiko.character.personality
        assert p.is_high("extraversion"), f"extraversion={p.extraversion}, expected high"
        assert p.is_high("agreeableness"), f"agreeableness={p.agreeableness}, expected high"
        assert p.is_low("neuroticism"), f"neuroticism={p.neuroticism}, expected low"

    def test_rin_personality_profile(self, sheets: list[CharacterSheet]) -> None:
        """Rin should be low extraversion, high openness, high conscientiousness."""
        rin = next(s for s in sheets if "rin" in s.character.id)
        p = rin.character.personality
        assert p.is_low("extraversion"), f"extraversion={p.extraversion}, expected low"
        assert p.is_high("openness"), f"openness={p.openness}, expected high"
        assert p.is_high("conscientiousness"), f"conscientiousness={p.conscientiousness}, expected high"

    def test_chiaki_personality_profile(self, sheets: list[CharacterSheet]) -> None:
        """Chiaki should be high extraversion, high openness, low conscientiousness."""
        chiaki = next(s for s in sheets if "chiaki" in s.character.id)
        p = chiaki.character.personality
        assert p.is_high("extraversion"), f"extraversion={p.extraversion}, expected high"
        assert p.is_high("openness"), f"openness={p.openness}, expected high"
        assert p.is_low("conscientiousness"), f"conscientiousness={p.conscientiousness}, expected low"


# ---------------------------------------------------------------------------
# Map YAML tests
# ---------------------------------------------------------------------------

class TestMapYAML:
    """Test that map.yaml loads correctly and defines expected locations."""

    @pytest.fixture
    def map_data(self) -> dict:
        text = MAP_PATH.read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def test_map_loads(self, map_data: dict) -> None:
        """map.yaml should parse as a valid dict."""
        assert isinstance(map_data, dict)

    def test_map_has_name(self, map_data: dict) -> None:
        assert "name" in map_data
        assert map_data["name"] == "野外活動サークル部室"

    def test_map_has_dimensions(self, map_data: dict) -> None:
        assert map_data["width"] == 20
        assert map_data["height"] == 15

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
        expected = {"table_a", "table_b", "bookshelf", "whiteboard", "window", "door"}
        assert expected.issubset(poi_ids), f"Missing POIs: {expected - poi_ids}"

    def test_hallway_location(self, map_data: dict) -> None:
        """Hallway location should exist."""
        hallway = next(
            (loc for loc in map_data["locations"] if loc["id"] == "hallway"),
            None,
        )
        assert hallway is not None
        assert hallway["name"] == "廊下"


# ---------------------------------------------------------------------------
# ScenarioLoader tests
# ---------------------------------------------------------------------------

class TestScenarioLoader:
    """Test ScenarioLoader creates valid WorldState from scenario data."""

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
        assert "name" in map_data
        assert "locations" in map_data

    def test_load_map_returns_locations(self, loader: ScenarioLoader) -> None:
        """load_map should return parseable location data."""
        map_data = loader.load_map()
        for loc in map_data["locations"]:
            assert "id" in loc
            assert "name" in loc
            assert "bounds" in loc

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
        assert len(state.locations) >= 1
        assert "clubroom" in state.locations
        for loc in state.locations.values():
            assert isinstance(loc, Location)

    def test_world_state_characters_placed_in_clubroom(self, loader: ScenarioLoader) -> None:
        """All characters should be initially placed in the clubroom."""
        state = loader.create_initial_world_state()
        for cs in state.characters.values():
            assert cs.location == "clubroom"
            assert cs.activity == "idle"

    def test_world_state_initial_tick(self, loader: ScenarioLoader) -> None:
        """WorldState should start at tick 0 with no active conversations."""
        state = loader.create_initial_world_state()
        assert state.tick == 0
        assert state.active_conversations == []

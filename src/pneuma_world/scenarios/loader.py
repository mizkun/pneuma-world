"""Scenario loader: reads character YAMLs and map definition from a scenario directory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from pneuma_core.character_sheet import CharacterSheet
from pneuma_core.models.character import Character
from pneuma_core.models.emotion import EmotionalState
from pneuma_core.models.goals import GoalTree
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, WorldState


class ScenarioLoader:
    """Load scenario data (characters + map) from a directory.

    Expected directory structure::

        scenario_dir/
            characters/
                *.character.yaml
            map.yaml
    """

    def __init__(self, scenario_dir: Path) -> None:
        self._dir = scenario_dir
        self._characters_dir = scenario_dir / "characters"
        self._map_path = scenario_dir / "map.yaml"

    def load_characters(self) -> list[Character]:
        """Load all character YAML files from characters/ subdirectory."""
        sheets = CharacterSheet.load_directory(self._characters_dir)
        return [sheet.character for sheet in sheets]

    def load_character_sheets(self) -> list[CharacterSheet]:
        """Load all CharacterSheets (character + goals + emotion) from characters/."""
        return CharacterSheet.load_directory(self._characters_dir)

    def extract_character_data(
        self,
    ) -> tuple[
        dict[str, Character],
        dict[str, GoalTree],
        dict[str, EmotionalState],
        dict[str, str],
    ]:
        """Extract all character data needed for ThinkCycle.

        Returns:
            Tuple of (characters, goal_trees, initial_emotions, character_names).
        """
        sheets = self.load_character_sheets()
        characters: dict[str, Character] = {}
        goal_trees: dict[str, GoalTree] = {}
        initial_emotions: dict[str, EmotionalState] = {}
        character_names: dict[str, str] = {}

        for sheet in sheets:
            char = sheet.character
            characters[char.id] = char
            character_names[char.id] = char.name
            if sheet.goal_tree:
                goal_trees[char.id] = sheet.goal_tree
            if sheet.initial_state:
                initial_emotions[char.id] = sheet.initial_state

        return characters, goal_trees, initial_emotions, character_names

    def load_map(self) -> dict:
        """Load map.yaml and return raw map data."""
        text = self._map_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("Invalid map YAML: expected a mapping")
        return data

    def _parse_locations(self, map_data: dict) -> dict[str, Location]:
        """Parse map data into Location objects."""
        locations: dict[str, Location] = {}
        for loc_data in map_data.get("locations", []):
            bounds_raw = loc_data["bounds"]
            bounds = (
                Position(x=bounds_raw[0][0], y=bounds_raw[0][1]),
                Position(x=bounds_raw[1][0], y=bounds_raw[1][1]),
            )
            locations[loc_data["id"]] = Location(
                id=loc_data["id"],
                name=loc_data["name"],
                bounds=bounds,
            )
        return locations

    def create_initial_world_state(self) -> WorldState:
        """Create a WorldState with all characters placed at default positions.

        Characters are placed in the first location defined in the map,
        spread across its points of interest if available.
        """
        characters = self.load_characters()
        map_data = self.load_map()
        locations = self._parse_locations(map_data)

        # Use the first location as the default spawn location
        first_loc_data = map_data["locations"][0]
        default_location_id = first_loc_data["id"]

        # Collect points of interest for initial placement
        pois = first_loc_data.get("points_of_interest", [])

        character_states: dict[str, CharacterState] = {}
        for i, char in enumerate(characters):
            # Place characters at different POIs if available, otherwise at (0, 0)
            if pois and i < len(pois):
                pos_raw = pois[i]["position"]
                position = Position(x=pos_raw[0], y=pos_raw[1])
            else:
                position = Position(x=0, y=0)

            character_states[char.id] = CharacterState(
                character_id=char.id,
                location=default_location_id,
                position=position,
                activity="idle",
            )

        return WorldState(
            tick=0,
            world_time=datetime.now(tz=timezone.utc),
            characters=character_states,
            active_conversations=[],
            locations=locations,
        )

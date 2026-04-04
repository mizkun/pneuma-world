"""ThinkCycle: the core autonomous thinking loop for characters."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from pneuma_core.llm.adapter import LLMAdapter, LLMRequest
from pneuma_core.models.character import Character
from pneuma_core.models.emotion import EmotionalState
from pneuma_core.models.goals import GoalTree
from pneuma_core.runtime.prompt_builder import PromptBuilder
from pneuma_world.models.action import ActionType, MiniAction, ThinkResult
from pneuma_world.models.action import ActionType, ThinkResult
from pneuma_world.models.event import WorldEvent
from pneuma_world.models.state import WorldState
from pneuma_world.tools import ToolRegistry
from pneuma_world.world_log import WorldLog

logger = logging.getLogger(__name__)

# Maximum number of recent thoughts to include in the prompt
MAX_THINK_HISTORY = 10


def _strip_markdown_code_block(text: str) -> str:
    """Strip markdown code block wrapping from LLM output.

    Haiku sometimes wraps JSON in ```json ... ``` blocks.
    """
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*\n(.*?)\n\s*```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def _build_situation_context(
    character_id: str,
    character_name: str,
    world_state: WorldState,
    character_names: dict[str, str] | None = None,
    pending_events: list[WorldEvent] | None = None,
) -> str:
    """Build a situation description from the world state."""
    char_state = world_state.characters.get(character_id)
    if char_state is None:
        return f"{character_name}の状態が見つかりません。"

    # Current location info
    location = world_state.locations.get(char_state.location)
    location_name = location.name if location else char_state.location

    # Nearby characters (same location)
    nearby = []
    for cid, cs in world_state.characters.items():
        if cid != character_id and cs.location == char_state.location:
            # Resolve to name if character_names available
            if character_names and cid in character_names:
                nearby.append(character_names[cid])
            else:
                nearby.append(cid)

    # Build context
    lines = [
        f"現在地: {location_name}",
        f"現在の活動: {char_state.activity}",
        f"ワールド時刻: {world_state.world_time.strftime('%Y-%m-%d %H:%M')}",
    ]
    if nearby:
        lines.append(f"近くにいるキャラクター: {', '.join(nearby)}")
    else:
        lines.append("近くに誰もいない")

    if char_state.conversation_id:
        lines.append(f"会話中: {char_state.conversation_id}")

    # Inject pending events relevant to this character
    if pending_events:
        relevant = [
            e for e in pending_events
            if e.target == "world" or e.target == character_id
        ]
        if relevant:
            lines.append("")
            lines.append("## 発生中のイベント")
            for event in relevant:
                lines.append(f"- [{event.type}] {event.content}")

    return "\n".join(lines)


def _build_think_history_section(history: list[ThinkResult]) -> str:
    """Format recent think history for the prompt."""
    if not history:
        return ""

    lines = ["## 直近の思考・行動"]
    for result in history:
        action = result.action_type.value
        if result.action_detail:
            action = f"{action}: {result.action_detail}"
        elif result.target_location:
            action = f"{action}: {result.target_location}"
        elif result.target_character_id:
            action = f"{action}: {result.target_character_id}"
        lines.append(f"- ({result.thought}) → {action}")

    return "\n".join(lines)


def _build_system_prompt(
    character_name: str,
    situation: str,
    available_tools: list[str],
    *,
    character_sections: str = "",
    think_history_section: str = "",
) -> str:
    """Build the system prompt for the think LLM call."""
    tool_section = ""
    if available_tools:
        tool_list = ", ".join(available_tools)
        tool_section = f"\n利用可能なツール: {tool_list}"

    # Build the prompt with character context if available
    parts = [f"あなたは「{character_name}」です。"]

    if character_sections:
        parts.append(character_sections)

    parts.append(f"## 状況\n{situation}{tool_section}")

    if think_history_section:
        parts.append(think_history_section)

    parts.append(
        "## 指示\n"
        "以上を踏まえて、内心の独白（thought）と次にとる行動（action_type）を決定してください。\n"
        "thoughtは必ずあなたのキャラクター・口調で書いてください。\n"
        "次にとる行動を複数ステップで記述してください（action_queue）。\n\n"
        "## 出力形式\n"
        "以下のJSON形式で応答してください。余分なテキストは含めないでください。\n\n"
        "{\n"
        '  "thought": "内心の独白（日本語、あなたの口調で）",\n'
        '  "action_type": "idle | move | solo_activity | start_conversation | use_tool",\n'
        '  "action_detail": "行動の詳細（省略可）",\n'
        '  "tool_name": "ツール名（use_toolの場合のみ）",\n'
        '  "tool_input": "ツールへの入力（use_toolの場合のみ）",\n'
        '  "target_character_id": "対象キャラID（start_conversationの場合のみ）",\n'
        '  "target_location": "移動先のlocation_id（moveの場合のみ）",\n'
        '  "action_queue": [\n'
        '    {"action": "walk_to | interact | sit | idle_animation", "target": "対象ID", "animation": "アニメーション名", "duration": 秒数}\n'
        "  ]\n"
        "}"
    )

    return "\n\n".join(parts)


def _parse_think_response(content: str) -> ThinkResult:
    """Parse the LLM response into a ThinkResult.

    If JSON parsing fails or the response contains an invalid action_type,
    returns a default IDLE ThinkResult with a fallback thought.
    """
    try:
        cleaned = _strip_markdown_code_block(content)
        data = json.loads(cleaned)

        # Parse action_queue with fallback to empty list
        action_queue: list[MiniAction] = []
        raw_queue = data.get("action_queue")
        if isinstance(raw_queue, list):
            try:
                action_queue = [
                    MiniAction(
                        action=item["action"],
                        target=item["target"],
                        animation=item["animation"],
                        duration=item["duration"],
                    )
                    for item in raw_queue
                ]
            except (KeyError, TypeError):
                action_queue = []

        return ThinkResult(
            thought=data.get("thought", ""),
            action_type=ActionType(data["action_type"]),
            action_detail=data.get("action_detail"),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            target_character_id=data.get("target_character_id"),
            target_location=data.get("target_location"),
            action_queue=action_queue,
        )
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("Failed to parse think response: %s (raw: %s)", e, content[:200])
        return ThinkResult(
            thought="（応答を解析できなかった）",
            action_type=ActionType.IDLE,
        )


class ThinkCycle:
    """The core autonomous thinking loop for a character.

    Executes one think cycle:
    1. Perceive: Build situation context from WorldState
    2. Think + Decide: Call LLM to think and decide action
    3. Act: Execute the decided action (may chain LLM calls)
    4. Log: Record to WorldLog

    ThinkCycle does NOT mutate WorldState. It returns ThinkResult,
    and the caller applies the changes.
    """

    def __init__(
        self,
        llm: LLMAdapter,
        tool_registry: ToolRegistry,
        world_log: WorldLog,
        think_model: str = "claude-haiku-4-5-20251001",
        action_model: str = "claude-sonnet-4-20250514",
        characters: dict[str, Character] | None = None,
        goal_trees: dict[str, GoalTree] | None = None,
        initial_emotions: dict[str, EmotionalState] | None = None,
        character_names: dict[str, str] | None = None,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry
        self._world_log = world_log
        self._think_model = think_model
        self._action_model = action_model
        self._characters = characters or {}
        self._goal_trees = goal_trees or {}
        self._emotions = dict(initial_emotions) if initial_emotions else {}
        self._character_names = character_names or {}
        self._prompt_builder = PromptBuilder()
        self._think_history: dict[str, list[ThinkResult]] = defaultdict(list)

    def _build_character_sections(self, character_id: str) -> str:
        """Build character identity sections using PromptBuilder."""
        character = self._characters.get(character_id)
        if character is None:
            return ""

        sections = [
            self._prompt_builder._build_profile_section(character),
            self._prompt_builder._build_personality_section(character),
            self._prompt_builder._build_values_section(character),
        ]

        # Goals
        goal_tree = self._goal_trees.get(character_id)
        if goal_tree:
            goals_section = self._prompt_builder._build_goals_section(goal_tree)
            if goals_section:
                sections.append(goals_section)

        # Emotional state
        emotion = self._emotions.get(character_id)
        if emotion:
            sections.append(self._prompt_builder._build_state_section(emotion))

        # Speaking style
        speaking_style = self._prompt_builder._build_speaking_style_section(character)
        if speaking_style:
            sections.append(speaking_style)

        return "\n\n".join(s for s in sections if s)

    async def execute(
        self,
        character_id: str,
        character_name: str,
        world_state: WorldState,
    ) -> ThinkResult:
        """Execute one think cycle for a character.

        Args:
            character_id: The character's unique ID.
            character_name: The character's display name.
            world_state: Current world state snapshot.

        Returns:
            ThinkResult describing what the character decided to do.
        """
        # 1. Perceive
        situation = _build_situation_context(
            character_id, character_name, world_state,
            character_names=self._character_names,
        )

        # 2. Build character context
        character_sections = self._build_character_sections(character_id)
        think_history_section = _build_think_history_section(
            self._think_history.get(character_id, [])
        )

        # 3. Think + Decide
        available_tools = [t.name for t in self._tool_registry.list_tools()]
        system_prompt = _build_system_prompt(
            character_name,
            situation,
            available_tools,
            character_sections=character_sections,
            think_history_section=think_history_section,
        )

        request = LLMRequest(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "次の行動を決定してください。"}],
            model=self._think_model,
            temperature=0.8,
            max_tokens=512,
        )

        response = await self._llm.generate(request)
        result = _parse_think_response(response.content)

        # 4. Record think history
        history = self._think_history[character_id]
        history.append(result)
        if len(history) > MAX_THINK_HISTORY:
            self._think_history[character_id] = history[-MAX_THINK_HISTORY:]

        # 5. Act
        await self._act(character_name, result, world_state)

        return result

    async def _act(
        self,
        character_name: str,
        result: ThinkResult,
        world_state: WorldState,
    ) -> None:
        """Execute the action phase and log results.

        This does NOT mutate WorldState -- it only logs and executes tools.
        """
        world_time = world_state.world_time

        if result.action_type == ActionType.IDLE:
            # Just log the thought
            self._world_log.record_thought(
                character_name, result.thought, world_time
            )

        elif result.action_type == ActionType.MOVE:
            # Log the movement action
            detail = result.action_detail or result.target_location or "移動"
            self._world_log.record_action(character_name, detail, world_time)

        elif result.action_type == ActionType.SOLO_ACTIVITY:
            # Log the activity
            detail = result.action_detail or "活動中"
            self._world_log.record_action(character_name, detail, world_time)

        elif result.action_type == ActionType.START_CONVERSATION:
            # Log the intent (actual conversation handled by InteractionBus)
            detail = result.action_detail or "会話を開始"
            self._world_log.record_action(character_name, detail, world_time)

        elif result.action_type == ActionType.USE_TOOL:
            # Execute the tool
            if result.tool_name:
                tool_result = await self._tool_registry.execute(
                    result.tool_name,
                    result.tool_input or "",
                    self._llm,
                )
                detail = result.action_detail or f"ツール実行: {result.tool_name}"
                self._world_log.record_action(character_name, detail, world_time)

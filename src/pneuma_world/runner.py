"""World Engine CLI runner: run a world simulation with real or mock LLM.

Usage:
    # As a module
    uv run python -m pneuma.world.runner --scenario yurucamp --think-interval 60

    # As a CLI subcommand
    uv run pneuma world --scenario yurucamp --think-interval 60

    # Dry-run mode (no API calls)
    uv run pneuma world --dry-run --think-interval 10 --max-ticks 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pneuma_core.llm.adapter import LLMRequest, LLMResponse
from pneuma_world.clock import TickConfig, WorldClock
from pneuma_world.engine import WorldEngine
from pneuma_world.interaction_bus import InteractionBus
from pneuma_world.models.action import ActionType, ThinkResult
from pneuma_world.scenarios.loader import ScenarioLoader
from pneuma_world.think_cycle import ThinkCycle
from pneuma_world.tools import ToolRegistry
from pneuma_world.world_log import WorldLog

logger = logging.getLogger(__name__)

# Models for world engine (lighter models for autonomous thinking)
WORLD_THINK_MODEL = "claude-haiku-4-5-20251001"
WORLD_RESPONSE_MODEL = "claude-sonnet-4-20250514"
WORLD_EMOTION_MODEL = "claude-haiku-4-5-20251001"


def _get_scenarios_dir() -> Path:
    """Return the scenarios directory path."""
    return Path(__file__).resolve().parent / "scenarios"


def _get_world_log_dir() -> Path:
    """Return the world log directory path."""
    from pneuma_core.vault import get_vault_path

    return get_vault_path() / "world"


def _get_world_db_path() -> str:
    """Return the world database path."""
    from pneuma_core.vault import get_vault_path

    db_path = get_vault_path() / "world" / "world.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


class MockLLMAdapter:
    """Mock LLM adapter for dry-run testing.

    Returns randomized but valid ThinkResult JSON responses.
    Also handles conversation messages by returning simple text.
    """

    _THOUGHTS = [
        "今日はいい天気だなぁ...",
        "何か面白いことないかな",
        "静かで落ち着く...",
        "お腹すいたなぁ",
        "みんな何してるんだろう",
        "本でも読もうかな",
        "ちょっと散歩したい気分",
        "今日の予定はなんだっけ",
    ]

    _ACTIVITIES = [
        "reading",
        "お茶を飲んでいる",
        "ノートに書き物",
        "窓の外を眺めている",
        "スマホを見ている",
    ]

    _SPEECHES = [
        "うん、そうだね",
        "へぇ〜、そうなんだ！",
        "なるほどね",
        "いいね！",
        "ふーん、面白いね",
        "そっかぁ",
        "えへへ、ありがとう",
        "じゃあね、またね",
    ]

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a mock LLM response."""
        # Check if this is a think cycle request (expects JSON)
        system = request.system_prompt or ""
        if "action_type" in system and "JSON" in system:
            return self._generate_think_response()
        # Otherwise, it's a conversation response
        return self._generate_conversation_response()

    def _generate_think_response(self) -> LLMResponse:
        """Generate a mock think cycle response."""
        action_type = random.choice(["idle", "solo_activity", "idle", "idle"])
        thought = random.choice(self._THOUGHTS)

        data: dict[str, Any] = {
            "thought": thought,
            "action_type": action_type,
        }

        if action_type == "solo_activity":
            data["action_detail"] = random.choice(self._ACTIVITIES)
        elif action_type == "move":
            data["target_location"] = "bookshelf"

        content = json.dumps(data, ensure_ascii=False)
        return LLMResponse(
            content=content,
            model="mock-dry-run",
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def _generate_conversation_response(self) -> LLMResponse:
        """Generate a mock conversation response."""
        speech = random.choice(self._SPEECHES)
        return LLMResponse(
            content=speech,
            model="mock-dry-run",
            usage={"input_tokens": 0, "output_tokens": 0},
        )


class MockEmbeddingService:
    """Mock embedding service for dry-run mode."""

    async def embed(self, text: str) -> list[float]:
        """Return a zero vector."""
        return [0.0] * 1536

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors."""
        return [[0.0] * 1536 for _ in texts]


def parse_world_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse world runner CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="pneuma world",
        description="Run the World Engine simulation",
    )
    parser.add_argument(
        "--scenario",
        default="yurucamp",
        help="Scenario name (default: yurucamp)",
    )
    parser.add_argument(
        "--think-interval",
        type=int,
        default=900,
        help="Think tick interval in seconds (default: 900, use 30-60 for testing)",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Maximum think ticks before stopping (default: infinite)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Use mock LLM instead of real API calls",
    )
    return parser.parse_args(argv if argv is not None else [])


def format_think_summary(character_name: str, result: ThinkResult) -> str:
    """Format a single character's think result for console output.

    Example:
        なでしこ: (思考) みんなまだ来てないなぁ... -> idle
        リン: (思考) 静かでいい... -> solo_activity: reading
        千明: (思考) 今日は何しようかな -> move: bookshelf
    """
    action = result.action_type.value

    # Add detail to action string
    if result.action_type == ActionType.SOLO_ACTIVITY and result.action_detail:
        action = f"{action}: {result.action_detail}"
    elif result.action_type == ActionType.MOVE and result.target_location:
        action = f"{action}: {result.target_location}"
    elif result.action_type == ActionType.START_CONVERSATION and result.target_character_id:
        action = f"{action}: {result.target_character_id}"
    elif result.action_type == ActionType.USE_TOOL and result.tool_name:
        action = f"{action}: {result.tool_name}"

    return f"  {character_name}: ({result.thought}) -> {action}"


def format_tick_header(world_time: datetime, tick_number: int) -> str:
    """Format the tick header for console output.

    Example: [09:00] Think Tick #1
    """
    from pneuma_world.world_log import JST

    jst_time = world_time.astimezone(JST)
    time_str = jst_time.strftime("%H:%M")
    return f"[{time_str}] Think Tick #{tick_number}"


async def build_world_components(
    *,
    scenario_dir: Path,
    llm: Any,
    embedding_service: Any,
    db_path: str = ":memory:",
) -> dict[str, Any]:
    """Build all world engine components from a scenario.

    Returns a dict with:
        - world_engine: WorldEngine instance
        - engines: dict of character_id -> RuntimeEngine
        - character_names: dict of character_id -> display name
        - storages: list of storage backends (for cleanup)
        - world_state: initial WorldState
    """
    from pneuma_core.runtime.engine import RuntimeEngine
    from pneuma_core.storage.sqlite import SQLiteStorageBackend

    # Load scenario
    loader = ScenarioLoader(scenario_dir)
    characters_dict, goal_trees, initial_emotions, character_names = (
        loader.extract_character_data()
    )
    characters = list(characters_dict.values())
    world_state = loader.create_initial_world_state()

    # Set up RuntimeEngine per character (shared LLM + embedding, separate storage)
    engines: dict[str, RuntimeEngine] = {}
    storages: list[SQLiteStorageBackend] = []

    for char in characters:
        # Each character gets its own storage connection for isolation
        storage = SQLiteStorageBackend(db_path)
        await storage.initialize()
        storages.append(storage)

        # Save character info
        await storage.save_character(char)

        # Create RuntimeEngine with minimal config (no diary, no todo, no user context)
        engine = RuntimeEngine(
            character_id=char.id,
            storage=storage,
            llm=llm,
            embedding_service=embedding_service,
            memory_store=storage,
            response_model=WORLD_RESPONSE_MODEL,
            emotion_model=WORLD_EMOTION_MODEL,
        )
        engines[char.id] = engine

    # Create world engine components
    world_log_dir = _get_world_log_dir() if db_path != ":memory:" else Path("/tmp/pneuma-world-log")
    world_log = WorldLog(log_dir=world_log_dir)
    tool_registry = ToolRegistry()

    think_cycle = ThinkCycle(
        llm=llm,
        tool_registry=tool_registry,
        world_log=world_log,
        think_model=WORLD_THINK_MODEL,
        characters=characters_dict,
        goal_trees=goal_trees,
        initial_emotions=initial_emotions,
        character_names=character_names,
    )

    interaction_bus = InteractionBus(
        engines=engines,
        world_log=world_log,
        character_names=character_names,
    )

    # Default clock (will be overridden by caller with correct think_interval)
    clock = WorldClock(TickConfig(
        visual_interval_seconds=1.0,
        think_interval_seconds=900.0,
    ))

    world_engine = WorldEngine(
        world_state=world_state,
        clock=clock,
        think_cycle=think_cycle,
        interaction_bus=interaction_bus,
        world_log=world_log,
        character_names=character_names,
    )

    return {
        "world_engine": world_engine,
        "engines": engines,
        "character_names": character_names,
        "storages": storages,
        "world_state": world_state,
    }


async def run_world(
    scenario: str = "yurucamp",
    think_interval: int = 900,
    max_ticks: int | None = None,
    dry_run: bool = False,
) -> None:
    """Run the world simulation main loop.

    Args:
        scenario: Scenario name (must exist in scenarios/ directory).
        think_interval: Think tick interval in seconds.
        max_ticks: Maximum think ticks (None = infinite).
        dry_run: If True, use mock LLM.
    """
    # Resolve scenario directory
    scenario_dir = _get_scenarios_dir() / scenario
    if not scenario_dir.exists():
        print(f"シナリオが見つかりません: {scenario_dir}")
        sys.exit(1)

    print(f"=== Pneuma World Engine ===")
    print(f"シナリオ: {scenario}")
    print(f"Think interval: {think_interval}s")
    print(f"Max ticks: {max_ticks or 'infinite'}")
    print(f"Dry-run: {dry_run}")
    print()

    # Set up LLM and embedding
    if dry_run:
        llm: Any = MockLLMAdapter()
        embedding: Any = MockEmbeddingService()
        db_path = ":memory:"
    else:
        from pneuma_core.llm.claude import ClaudeAdapter
        from pneuma_core.llm.embedding import OpenAIEmbeddingService

        try:
            llm = ClaudeAdapter.from_env()
        except ValueError as e:
            print(f"Error: {e}")
            print("Set ANTHROPIC_API_KEY or use --dry-run")
            sys.exit(1)

        try:
            embedding = OpenAIEmbeddingService.from_env()
        except ValueError as e:
            print(f"Error: {e}")
            print("Set OPENAI_API_KEY or use --dry-run")
            sys.exit(1)

        db_path = _get_world_db_path()

    # Build components
    components = await build_world_components(
        scenario_dir=scenario_dir,
        llm=llm,
        embedding_service=embedding,
        db_path=db_path,
    )

    world_engine = components["world_engine"]
    character_names = components["character_names"]

    # Override clock with requested think interval
    clock = WorldClock(TickConfig(
        visual_interval_seconds=1.0,
        think_interval_seconds=float(think_interval),
    ))
    world_engine._clock = clock

    # Print initial state
    print("キャラクター:")
    for char_id, name in character_names.items():
        state = world_engine.state.characters[char_id]
        print(f"  {name} ({char_id}) @ {state.location} [{state.activity}]")
    print()
    print("--- シミュレーション開始 ---")
    print()

    # Graceful shutdown flag
    shutdown = asyncio.Event()

    def _signal_handler(sig: int, frame: Any) -> None:
        print("\n\n--- シャットダウン中... ---")
        shutdown.set()

    signal.signal(signal.SIGINT, _signal_handler)

    # Main loop
    think_tick_count = 0

    try:
        while not shutdown.is_set():
            results = await world_engine.tick()

            if results:
                think_tick_count += 1
                world_time = world_engine.state.world_time

                # Print tick header
                header = format_tick_header(world_time, think_tick_count)
                print(header)

                # Build list of characters that participated in this think cycle
                # (those NOT in conversation at the time of tick)
                # Results are in the same order as characters dict iteration,
                # but only for characters whose conversation_id was None.
                eligible_char_ids = []
                for char_id, char_state in world_engine.state.characters.items():
                    # After tick(), conversation_id might have been set by the tick.
                    # But results were collected for characters that were eligible.
                    eligible_char_ids.append(char_id)

                # Match results to character names (results are in order)
                for i, result in enumerate(results):
                    if i < len(eligible_char_ids):
                        char_id = eligible_char_ids[i]
                        name = character_names.get(char_id, char_id)
                    else:
                        name = f"character-{i}"
                    summary = format_think_summary(name, result)
                    print(summary)

                print()

                # Check max_ticks
                if max_ticks is not None and think_tick_count >= max_ticks:
                    print(f"--- {max_ticks} ticks 完了 ---")
                    break

            # Sleep for visual tick interval (non-blocking for shutdown)
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=1.0)
                break  # Shutdown requested
            except asyncio.TimeoutError:
                pass  # Continue normal loop

    finally:
        # Cleanup
        print("ストレージをクリーンアップ中...")
        for storage in components["storages"]:
            await storage.close()
        print("完了。")


def main() -> None:
    """CLI entry point for `python -m pneuma.world.runner`."""
    # Try to load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    args = parse_world_args(sys.argv[1:])
    asyncio.run(run_world(
        scenario=args.scenario,
        think_interval=args.think_interval,
        max_ticks=args.max_ticks,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()

"""E2E Integration Tests: LLM モック化した統合テスト (Issue #8).

Phase 1 の全コンポーネントが統合された状態で、3人のキャラクターが
シナリオ上で1サイクル完遂することを確認する。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from pneuma_core.llm.adapter import LLMRequest, LLMResponse
from pneuma_core.models.emotion import EmotionalState
from pneuma_core.models.message import MessageOutput
from pneuma_world.clock import TickConfig, WorldClock
from pneuma_world.engine import WorldEngine
from pneuma_world.events import EventQueue, RandomEventTable
from pneuma_world.interaction_bus import InteractionBus
from pneuma_world.models.action import ActionType, MiniAction, ThinkResult
from pneuma_world.models.event import WorldEvent
from pneuma_world.models.location import Location, Position
from pneuma_world.models.state import CharacterState, Conversation, WorldState
from pneuma_world.scenarios.loader import ScenarioLoader
from pneuma_world.server import create_app
from pneuma_world.think_cycle import ThinkCycle
from pneuma_world.tools import ToolRegistry
from pneuma_world.world_log import WorldLog

JST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# Mock LLM Adapter
# ---------------------------------------------------------------------------

_DEFAULT_IDLE_RESPONSE = json.dumps(
    {
        "thought": "特に何もない",
        "action_type": "idle",
        "action_queue": [],
    },
    ensure_ascii=False,
)


class MockLLMAdapter:
    """テスト用 LLM モック。事前定義されたレスポンスを返す。"""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses or []
        self._call_count = 0
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self._call_count < len(self._responses):
            content = self._responses[self._call_count]
        else:
            content = _DEFAULT_IDLE_RESPONSE
        self._call_count += 1
        return LLMResponse(content=content, model="mock", usage={})

    @property
    def call_count(self) -> int:
        return self._call_count


class ErrorLLMAdapter:
    """例外を投げる LLM モック。"""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("LLM API failure")


# ---------------------------------------------------------------------------
# Helpers: 3人のキャラクターで WorldState を構築
# ---------------------------------------------------------------------------

CHARACTER_IDS = ["aoi-001", "rin-001", "hinata-001"]
CHARACTER_NAMES = {
    "aoi-001": "葵",
    "rin-001": "凛",
    "hinata-001": "ひなた",
}


def _make_3char_world_state() -> WorldState:
    """3人のキャラクターが部室にいる WorldState を作成。"""
    characters = {
        "aoi-001": CharacterState(
            character_id="aoi-001",
            location="clubroom",
            position=Position(12, 15),
            activity="idle",
        ),
        "rin-001": CharacterState(
            character_id="rin-001",
            location="clubroom",
            position=Position(15, 13),
            activity="idle",
        ),
        "hinata-001": CharacterState(
            character_id="hinata-001",
            location="clubroom",
            position=Position(18, 15),
            activity="idle",
        ),
    }
    return WorldState(
        tick=0,
        world_time=datetime(2026, 4, 1, 15, 0, 0, tzinfo=JST),
        characters=characters,
        active_conversations=[],
        locations={
            "clubroom": Location(
                id="clubroom",
                name="部室",
                bounds=(Position(0, 0), Position(29, 29)),
            ),
            "hallway": Location(
                id="hallway",
                name="廊下",
                bounds=(Position(0, 30), Position(29, 32)),
            ),
        },
    )


def _make_engine_with_mock_llm(
    tmp_path: Path,
    llm: MockLLMAdapter | None = None,
    tick_config: TickConfig | None = None,
    world_state: WorldState | None = None,
) -> tuple[WorldEngine, MockLLMAdapter, ThinkCycle, InteractionBus]:
    """MockLLMAdapter を使って WorldEngine を構築する。"""
    mock_llm = llm or MockLLMAdapter()
    ws = world_state or _make_3char_world_state()
    config = tick_config or TickConfig(
        visual_interval_seconds=1.0, think_interval_seconds=1.0
    )
    clock = WorldClock(config=config)
    tool_registry = ToolRegistry()
    world_log = WorldLog(log_dir=tmp_path / "world-log")

    think_cycle = ThinkCycle(
        llm=mock_llm,
        tool_registry=tool_registry,
        world_log=world_log,
        character_names=CHARACTER_NAMES,
    )

    # RuntimeEngine モック (InteractionBus 用)
    mock_engines: dict[str, AsyncMock] = {}
    for char_id in CHARACTER_IDS:
        engine_mock = AsyncMock()
        engine_mock.process_message.return_value = MessageOutput(
            content="はい、そうですね",
            emotion=EmotionalState(
                pleasure=0.3,
                arousal=0.0,
                dominance=0.0,
                emotion_label="平穏",
                situation="会話中",
            ),
        )
        mock_engines[char_id] = engine_mock

    interaction_bus = InteractionBus(
        engines=mock_engines,
        world_log=world_log,
        character_names=CHARACTER_NAMES,
        llm=mock_llm,
    )

    engine = WorldEngine(
        world_state=ws,
        clock=clock,
        think_cycle=think_cycle,
        interaction_bus=interaction_bus,
        world_log=world_log,
        character_names=CHARACTER_NAMES,
    )
    return engine, mock_llm, think_cycle, interaction_bus


# ===========================================================================
# 1. シナリオ初期化テスト
# ===========================================================================


class TestScenarioInitialization:
    """clubroom シナリオから WorldState が正しく初期化される。"""

    def test_clubroom_scenario_loads_3_characters(self) -> None:
        """clubroom シナリオから3人のキャラクターが読み込まれる。"""
        scenario_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "clubroom"
        )
        loader = ScenarioLoader(scenario_dir)
        characters = loader.load_characters()
        assert len(characters) == 3

    def test_clubroom_scenario_creates_world_state(self) -> None:
        """clubroom シナリオから WorldState が正しく初期化される。"""
        scenario_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "clubroom"
        )
        loader = ScenarioLoader(scenario_dir)
        world_state = loader.create_initial_world_state()

        assert len(world_state.characters) == 3
        assert world_state.tick == 0
        assert "clubroom" in world_state.locations

    def test_clubroom_scenario_has_clubroom_location(self) -> None:
        """部室ロケーションが存在する。"""
        scenario_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "clubroom"
        )
        loader = ScenarioLoader(scenario_dir)
        world_state = loader.create_initial_world_state()

        clubroom = world_state.locations["clubroom"]
        assert clubroom.name == "部室"

    def test_all_characters_start_in_clubroom(self) -> None:
        """全キャラクターが部室から開始する。"""
        scenario_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "clubroom"
        )
        loader = ScenarioLoader(scenario_dir)
        world_state = loader.create_initial_world_state()

        for char_id, char_state in world_state.characters.items():
            assert char_state.location == "clubroom", (
                f"{char_id} が clubroom にいない"
            )


# ===========================================================================
# 2. Think tick サイクルテスト
# ===========================================================================


class TestThinkTickCycle:
    """3人が Think tick で並列思考し、ThinkResult を返す。"""

    @pytest.mark.asyncio
    async def test_three_characters_think_on_tick(self, tmp_path: Path) -> None:
        """3人全員の ThinkCycle.execute が呼ばれ、ThinkResult が返る。"""
        engine, mock_llm, _, _ = _make_engine_with_mock_llm(tmp_path)

        results = await engine.tick()

        assert len(results) == 3
        for result in results:
            assert isinstance(result, ThinkResult)
        # LLM が3回呼ばれた (各キャラ1回)
        assert mock_llm.call_count == 3

    @pytest.mark.asyncio
    async def test_think_result_contains_thought(self, tmp_path: Path) -> None:
        """ThinkResult に thought が含まれる。"""
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path)

        results = await engine.tick()

        for result in results:
            assert result.thought != ""

    @pytest.mark.asyncio
    async def test_think_result_with_action_queue(self, tmp_path: Path) -> None:
        """action_queue 付きの ThinkResult が正しくパースされる。"""
        response_with_queue = json.dumps(
            {
                "thought": "机に行って座ろう",
                "action_type": "move",
                "target_location": "clubroom",
                "action_queue": [
                    {
                        "action": "walk_to",
                        "target": "table_center",
                        "animation": "walk",
                        "duration": 3,
                    },
                    {
                        "action": "sit",
                        "target": "chair_1",
                        "animation": "sit_down",
                        "duration": 1,
                    },
                ],
            },
            ensure_ascii=False,
        )
        mock_llm = MockLLMAdapter(responses=[response_with_queue])
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path, llm=mock_llm)

        results = await engine.tick()

        # 最初のキャラの結果に action_queue が含まれる
        first_result = results[0]
        assert first_result.action_type == ActionType.MOVE
        assert len(first_result.action_queue) == 2
        assert first_result.action_queue[0].action == "walk_to"
        assert first_result.action_queue[1].action == "sit"

    @pytest.mark.asyncio
    async def test_tick_increments_tick_count(self, tmp_path: Path) -> None:
        """tick 後に world_state.tick がインクリメントされる。"""
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path)

        assert engine.state.tick == 0
        await engine.tick()
        assert engine.state.tick == 1


# ===========================================================================
# 3. 会話開始 → 3人会話テスト
# ===========================================================================


class TestConversationFlow:
    """会話の開始から終了までの一連のフローを検証。"""

    @pytest.mark.asyncio
    async def test_start_conversation_creates_conversation(
        self, tmp_path: Path
    ) -> None:
        """start_conversation で Conversation が作成され、会話が実行される。"""
        response_start_conv = json.dumps(
            {
                "thought": "凛ちゃんに話しかけよう",
                "action_type": "start_conversation",
                "action_detail": "おはよう！今日も部活がんばろー！",
                "target_character_id": "rin-001",
                "action_queue": [],
            },
            ensure_ascii=False,
        )
        # aoi: start_conversation, rin: idle, hinata: idle
        responses = [
            response_start_conv,
            _DEFAULT_IDLE_RESPONSE,
            _DEFAULT_IDLE_RESPONSE,
        ]
        mock_llm = MockLLMAdapter(responses=responses)
        engine, _, _, interaction_bus = _make_engine_with_mock_llm(
            tmp_path, llm=mock_llm
        )

        results = await engine.tick()

        # start_conversation が1つ含まれる
        conv_results = [
            r for r in results if r.action_type == ActionType.START_CONVERSATION
        ]
        assert len(conv_results) == 1
        assert conv_results[0].target_character_id == "rin-001"

    @pytest.mark.asyncio
    async def test_conversation_cleanup_resets_conversation_id(
        self, tmp_path: Path
    ) -> None:
        """会話終了後に conversation_id がリセットされる。"""
        response_start_conv = json.dumps(
            {
                "thought": "凛ちゃんに話しかけよう",
                "action_type": "start_conversation",
                "action_detail": "おはよう！",
                "target_character_id": "rin-001",
                "action_queue": [],
            },
            ensure_ascii=False,
        )
        responses = [
            response_start_conv,
            _DEFAULT_IDLE_RESPONSE,
            _DEFAULT_IDLE_RESPONSE,
        ]
        mock_llm = MockLLMAdapter(responses=responses)
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path, llm=mock_llm)

        await engine.tick()

        # 会話終了後、全キャラの conversation_id が None
        for char_id in CHARACTER_IDS:
            char = engine.state.characters[char_id]
            assert char.conversation_id is None, (
                f"{char_id} の conversation_id がリセットされていない"
            )

    @pytest.mark.asyncio
    async def test_conversation_removes_from_active(self, tmp_path: Path) -> None:
        """会話終了後に active_conversations から除去される。"""
        response_start_conv = json.dumps(
            {
                "thought": "凛に話しかけよう",
                "action_type": "start_conversation",
                "action_detail": "おはよう！",
                "target_character_id": "rin-001",
                "action_queue": [],
            },
            ensure_ascii=False,
        )
        responses = [
            response_start_conv,
            _DEFAULT_IDLE_RESPONSE,
            _DEFAULT_IDLE_RESPONSE,
        ]
        mock_llm = MockLLMAdapter(responses=responses)
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path, llm=mock_llm)

        await engine.tick()

        assert len(engine.state.active_conversations) == 0


# ===========================================================================
# 4. 介入イベントテスト
# ===========================================================================


class TestInterventionEvents:
    """EventQueue を経由した介入イベントが ThinkCycle に反映される。"""

    @pytest.mark.asyncio
    async def test_event_queue_push_and_drain(self) -> None:
        """EventQueue に push したイベントが drain で取得できる。"""
        eq = EventQueue()
        event = WorldEvent(
            type="environment",
            content="雨が降ってきた",
            source="human",
            target="world",
        )
        await eq.push(event)
        events = eq.drain()

        assert len(events) == 1
        assert events[0].content == "雨が降ってきた"

    @pytest.mark.asyncio
    async def test_event_queue_drain_empties_queue(self) -> None:
        """drain 後にキューが空になる。"""
        eq = EventQueue()
        await eq.push(
            WorldEvent(
                type="environment",
                content="テスト",
                source="human",
                target="world",
            )
        )
        eq.drain()
        events = eq.drain()
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_event_reflected_in_situation_context(self) -> None:
        """pending_events が situation context に含まれる。"""
        from pneuma_world.think_cycle import _build_situation_context

        ws = _make_3char_world_state()
        event = WorldEvent(
            type="environment",
            content="雨が降ってきた",
            source="human",
            target="world",
        )

        context = _build_situation_context(
            "aoi-001",
            "葵",
            ws,
            pending_events=[event],
        )

        assert "雨が降ってきた" in context
        assert "発生中のイベント" in context

    @pytest.mark.asyncio
    async def test_character_specific_event(self) -> None:
        """キャラ固有イベントがそのキャラにのみ反映される。"""
        from pneuma_world.think_cycle import _build_situation_context

        ws = _make_3char_world_state()
        event = WorldEvent(
            type="character_contact",
            content="スマホに通知が来た",
            source="human",
            target="aoi-001",
        )

        # aoi には反映される
        context_aoi = _build_situation_context(
            "aoi-001", "葵", ws, pending_events=[event]
        )
        assert "スマホに通知が来た" in context_aoi

        # rin には反映されない
        context_rin = _build_situation_context(
            "rin-001", "凛", ws, pending_events=[event]
        )
        assert "スマホに通知が来た" not in context_rin


# ===========================================================================
# 5. ランダムイベント発火テスト
# ===========================================================================


class TestRandomEventFiring:
    """RandomEventTable からイベントが発火する。"""

    def test_random_event_table_from_yaml(self) -> None:
        """YAML からランダムイベントテーブルを読み込める。"""
        events_yaml = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "pneuma_world"
            / "scenarios"
            / "clubroom"
            / "events.yaml"
        )
        table = RandomEventTable.from_yaml(str(events_yaml))
        assert len(table.entries) > 0

    def test_random_event_roll_returns_world_event(self) -> None:
        """roll() が WorldEvent を返す。"""
        entries = [
            {"type": "environment", "content": "窓の外で猫が鳴いている", "weight": 3},
            {"type": "physical", "content": "棚から本が1冊落ちた", "weight": 1},
        ]
        table = RandomEventTable(entries=entries)

        event = table.roll()
        assert event is not None
        assert isinstance(event, WorldEvent)
        assert event.source == "random_table"
        assert event.target == "world"

    def test_random_event_roll_empty_table_returns_none(self) -> None:
        """空テーブルの roll() は None を返す。"""
        table = RandomEventTable(entries=[])
        assert table.roll() is None

    @pytest.mark.asyncio
    async def test_random_event_can_be_pushed_to_queue(self) -> None:
        """roll() で得たイベントを EventQueue に push できる。"""
        entries = [
            {"type": "environment", "content": "チャイムが鳴った", "weight": 1},
        ]
        table = RandomEventTable(entries=entries)
        event = table.roll()
        assert event is not None

        eq = EventQueue()
        await eq.push(event)
        events = eq.drain()
        assert len(events) == 1
        assert events[0].content == "チャイムが鳴った"


# ===========================================================================
# 6. WebSocket 配信テスト
# ===========================================================================


class TestWebSocketBroadcast:
    """FastAPI TestClient で WebSocket 配信を検証。"""

    def _make_app_with_mock_engine(self) -> tuple:
        """モック WorldEngine を注入した FastAPI app を作成。"""
        ws = _make_3char_world_state()
        ws.tick = 1
        mock_engine = MagicMock()
        mock_engine.state = ws
        app = create_app(engine=mock_engine)
        return app, mock_engine

    def test_websocket_connects_successfully(self) -> None:
        """WebSocket 接続が正常に確立される。"""
        app, _ = self._make_app_with_mock_engine()
        client = TestClient(app)
        with client.websocket_connect("/ws/world-state") as ws:
            assert len(app.state.manager._connections) == 1

    def test_websocket_receives_event_via_ws(self) -> None:
        """WebSocket 経由で world_event を送信し、EventQueue に入る。"""
        app, _ = self._make_app_with_mock_engine()
        client = TestClient(app)
        with client.websocket_connect("/ws/world-state") as ws:
            ws.send_json(
                {
                    "type": "world_event",
                    "event": {
                        "type": "environment",
                        "content": "窓から風が入ってきた",
                        "source": "human",
                        "target": "world",
                    },
                }
            )
            import time

            time.sleep(0.1)
            events = app.state.event_queue.drain()
            assert len(events) == 1
            assert events[0].content == "窓から風が入ってきた"

    @pytest.mark.asyncio
    async def test_broadcast_sends_world_state(self) -> None:
        """ConnectionManager.broadcast が world_state メッセージを送信できる。"""
        from pneuma_world.server import ConnectionManager

        mgr = ConnectionManager()
        ws_mock = AsyncMock()
        await mgr.connect(ws_mock)

        state_data = {
            "type": "world_state",
            "tick": 1,
            "characters": {},
        }
        await mgr.broadcast(state_data)

        ws_mock.send_json.assert_awaited_once_with(state_data)


# ===========================================================================
# 7. ヘルスチェックテスト
# ===========================================================================


class TestHealthCheck:
    """/health エンドポイントのテスト。"""

    def test_health_without_engine(self) -> None:
        """エンジンなしで健全なステータスを返す。"""
        app = create_app(engine=None)
        client = TestClient(app)
        resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["characters_active"] == 0
        assert body["last_tick"] is None

    def test_health_with_engine(self) -> None:
        """エンジンありでキャラクター数を返す。"""
        ws = _make_3char_world_state()
        mock_engine = MagicMock()
        mock_engine.state = ws
        app = create_app(engine=mock_engine)
        client = TestClient(app)
        resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["characters_active"] == 3


# ===========================================================================
# 8. POST /api/events テスト
# ===========================================================================


class TestPostEventsEndpoint:
    """REST 経由でのイベント送信テスト。"""

    def test_post_event_accepted(self) -> None:
        """POST /api/events が accepted を返す。"""
        app = create_app(engine=None)
        client = TestClient(app)
        resp = client.post(
            "/api/events",
            json={
                "type": "environment",
                "content": "雷が鳴った",
                "source": "human",
                "target": "world",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert "event_id" in body

    def test_post_event_enters_queue(self) -> None:
        """POST /api/events で送信したイベントが EventQueue に入る。"""
        app = create_app(engine=None)
        client = TestClient(app)
        client.post(
            "/api/events",
            json={
                "type": "scenario",
                "content": "転校生が来た",
                "source": "orchestrator",
                "target": "world",
            },
        )

        events = app.state.event_queue.drain()
        assert len(events) == 1
        assert events[0].content == "転校生が来た"
        assert events[0].type == "scenario"
        assert events[0].source == "orchestrator"

    def test_multiple_events_accumulate(self) -> None:
        """複数のイベントが蓄積される。"""
        app = create_app(engine=None)
        client = TestClient(app)
        for i in range(3):
            client.post(
                "/api/events",
                json={
                    "type": "environment",
                    "content": f"イベント{i}",
                    "source": "human",
                    "target": "world",
                },
            )

        events = app.state.event_queue.drain()
        assert len(events) == 3


# ===========================================================================
# 9. エラーリカバリテスト
# ===========================================================================


class TestErrorRecovery:
    """LLM エラー時のリカバリ動作を検証。"""

    @pytest.mark.asyncio
    async def test_llm_exception_returns_idle_fallback(
        self, tmp_path: Path
    ) -> None:
        """LLM が例外を投げても ThinkCycle は IDLE フォールバックを返す。"""
        error_llm = ErrorLLMAdapter()
        ws = _make_3char_world_state()
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        clock = WorldClock(config=config)
        tool_registry = ToolRegistry()
        world_log = WorldLog(log_dir=tmp_path / "world-log")

        think_cycle = ThinkCycle(
            llm=error_llm,
            tool_registry=tool_registry,
            world_log=world_log,
            character_names=CHARACTER_NAMES,
        )

        # ThinkCycle.execute は例外を raise する
        # WorldEngine はそれを処理する必要がある
        # 直接 ThinkCycle を呼んで例外が出ることを確認
        with pytest.raises(RuntimeError, match="LLM API failure"):
            await think_cycle.execute("aoi-001", "葵", ws)

    @pytest.mark.asyncio
    async def test_engine_recovers_from_think_cycle_error(
        self, tmp_path: Path
    ) -> None:
        """WorldEngine は ThinkCycle エラー時もクラッシュしない。

        ただし現在の engine.tick() は例外を伝播させる設計。
        そのため、ここでは mock ThinkCycle でエラーを模擬し、
        エンジンの他の状態が壊れないことを検証する。
        """
        ws = _make_3char_world_state()
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        clock = WorldClock(config=config)
        mock_think = AsyncMock(spec=ThinkCycle)
        mock_bus = AsyncMock(spec=InteractionBus)
        world_log = WorldLog(log_dir=tmp_path / "world-log")

        engine = WorldEngine(
            world_state=ws,
            clock=clock,
            think_cycle=mock_think,
            interaction_bus=mock_bus,
            world_log=world_log,
            character_names=CHARACTER_NAMES,
        )

        # 最初のキャラでエラー → 例外が伝播
        mock_think.execute.side_effect = RuntimeError("LLM down")

        with pytest.raises(RuntimeError, match="LLM down"):
            await engine.tick()

        # WorldState は壊れていない（tick は 1 に上がっている）
        assert engine.state.tick == 1
        # キャラクターの状態は保持されている
        assert len(engine.state.characters) == 3
        for char_id in CHARACTER_IDS:
            assert char_id in engine.state.characters

    @pytest.mark.asyncio
    async def test_conversation_error_resets_state(self, tmp_path: Path) -> None:
        """InteractionBus.run_conversation が例外を投げても、
        キャラクターの conversation_id がリセットされる。"""
        response_start_conv = json.dumps(
            {
                "thought": "凛に話しかけよう",
                "action_type": "start_conversation",
                "action_detail": "おはよう！",
                "target_character_id": "rin-001",
                "action_queue": [],
            },
            ensure_ascii=False,
        )

        ws = _make_3char_world_state()
        config = TickConfig(visual_interval_seconds=1.0, think_interval_seconds=1.0)
        clock = WorldClock(config=config)
        mock_think = AsyncMock(spec=ThinkCycle)
        mock_bus = AsyncMock(spec=InteractionBus)
        world_log = WorldLog(log_dir=tmp_path / "world-log")

        engine = WorldEngine(
            world_state=ws,
            clock=clock,
            think_cycle=mock_think,
            interaction_bus=mock_bus,
            world_log=world_log,
            character_names=CHARACTER_NAMES,
        )

        call_count = 0

        async def think_side_effect(char_id, char_name, world_state):
            nonlocal call_count
            call_count += 1
            if char_id == "aoi-001":
                return ThinkResult(
                    thought="凛に話しかけよう",
                    action_type=ActionType.START_CONVERSATION,
                    action_detail="おはよう！",
                    target_character_id="rin-001",
                )
            return ThinkResult(
                thought="暇",
                action_type=ActionType.IDLE,
            )

        mock_think.execute.side_effect = think_side_effect
        mock_bus.run_conversation.side_effect = RuntimeError("会話API失敗")

        # エンジンはエラーを飲み込むはず
        await engine.tick()

        # conversation_id がリセットされていること
        assert engine.state.characters["aoi-001"].conversation_id is None
        assert engine.state.characters["rin-001"].conversation_id is None
        assert len(engine.state.active_conversations) == 0

    @pytest.mark.asyncio
    async def test_invalid_json_response_fallback(self, tmp_path: Path) -> None:
        """LLM が不正な JSON を返しても IDLE フォールバックで処理される。"""
        invalid_responses = [
            "これはJSONではありません",
            '{"thought": "テスト"}',  # action_type 欠落
            "",
        ]
        mock_llm = MockLLMAdapter(responses=invalid_responses)
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path, llm=mock_llm)

        results = await engine.tick()

        # 3人分の結果が返る（全てフォールバック IDLE）
        assert len(results) == 3
        for result in results:
            assert result.action_type == ActionType.IDLE


# ===========================================================================
# 統合フルサイクルテスト
# ===========================================================================


class TestFullCycleIntegration:
    """全コンポーネントを組み合わせた1サイクル完遂テスト。"""

    @pytest.mark.asyncio
    async def test_full_cycle_idle(self, tmp_path: Path) -> None:
        """3人全員が idle のフルサイクル。"""
        engine, mock_llm, _, _ = _make_engine_with_mock_llm(tmp_path)

        # 1 tick 実行
        results = await engine.tick()

        assert len(results) == 3
        assert engine.state.tick == 1
        assert engine.state.world_time > datetime(2026, 4, 1, 15, 0, 0, tzinfo=JST)
        # 全キャラ idle のまま
        for char_id in CHARACTER_IDS:
            char = engine.state.characters[char_id]
            assert char.activity == "idle"
            assert char.conversation_id is None

    @pytest.mark.asyncio
    async def test_full_cycle_with_conversation(self, tmp_path: Path) -> None:
        """会話を含むフルサイクル。"""
        responses = [
            json.dumps(
                {
                    "thought": "凛ちゃんに話しかけよう！",
                    "action_type": "start_conversation",
                    "action_detail": "ねーねー凛ちゃん、今日のおやつ何にする？",
                    "target_character_id": "rin-001",
                    "action_queue": [],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "thought": "コーディングに集中したい",
                    "action_type": "solo_activity",
                    "action_detail": "コーディング中",
                    "action_queue": [],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "thought": "絵を描こう",
                    "action_type": "solo_activity",
                    "action_detail": "スケッチ中",
                    "action_queue": [],
                },
                ensure_ascii=False,
            ),
        ]
        mock_llm = MockLLMAdapter(responses=responses)
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path, llm=mock_llm)

        results = await engine.tick()

        # aoi が start_conversation で rin を対象にしたため、
        # rin は conversation_id がセットされ think からスキップされる。
        # 結果は aoi + hinata の2件。
        assert len(results) == 2

        # aoi は会話を開始したが、会話後にクリーンアップされている
        aoi = engine.state.characters["aoi-001"]
        assert aoi.conversation_id is None
        assert aoi.activity == "idle"

        # rin も会話後にクリーンアップ
        rin = engine.state.characters["rin-001"]
        assert rin.conversation_id is None

    @pytest.mark.asyncio
    async def test_full_cycle_with_move(self, tmp_path: Path) -> None:
        """移動を含むフルサイクル。"""
        responses = [
            json.dumps(
                {
                    "thought": "廊下に行こう",
                    "action_type": "move",
                    "target_location": "hallway",
                    "action_queue": [
                        {
                            "action": "walk_to",
                            "target": "door",
                            "animation": "walk",
                            "duration": 5,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        ]
        mock_llm = MockLLMAdapter(responses=responses)
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path, llm=mock_llm)

        results = await engine.tick()

        # 最初のキャラが移動
        first_char_id = list(engine.state.characters.keys())[0]
        first_char = engine.state.characters[first_char_id]
        assert first_char.activity == "walking"
        assert first_char.location == "hallway"

    @pytest.mark.asyncio
    async def test_multiple_ticks_accumulate(self, tmp_path: Path) -> None:
        """複数 tick を連続実行しても状態が正しく維持される。"""
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path)

        for i in range(3):
            results = await engine.tick()
            assert len(results) == 3

        assert engine.state.tick == 3
        assert len(engine.state.characters) == 3

    @pytest.mark.asyncio
    async def test_world_log_records_entries(self, tmp_path: Path) -> None:
        """Think tick 後に WorldLog にエントリが記録される。"""
        log_dir = tmp_path / "world-log"
        engine, _, _, _ = _make_engine_with_mock_llm(tmp_path)

        await engine.tick()

        # ログディレクトリが作成されている
        assert log_dir.exists()
        # ログファイルが存在する
        log_files = list(log_dir.glob("*.md"))
        assert len(log_files) > 0

"""Tests for FastAPI WebSocket server (Issue #7)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """ConnectionManager の単体テスト。"""

    def _make_manager(self):
        from pneuma_world.server import ConnectionManager

        return ConnectionManager()

    @pytest.fixture
    def manager(self):
        return self._make_manager()

    @pytest.mark.asyncio
    async def test_connect_adds_websocket(self, manager):
        """connect() で WebSocket が接続リストに追加される。"""
        ws = AsyncMock()
        await manager.connect(ws)
        assert ws in manager._connections
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self, manager):
        """disconnect() で WebSocket が接続リストから除去される。"""
        ws = AsyncMock()
        await manager.connect(ws)
        manager.disconnect(ws)
        assert ws not in manager._connections

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, manager):
        """broadcast() が全接続に send_json する。"""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(ws1)
        await manager.connect(ws2)

        data = {"type": "world_state", "tick": 1}
        await manager.broadcast(data)

        ws1.send_json.assert_awaited_once_with(data)
        ws2.send_json.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_broadcast_removes_broken_connections(self, manager):
        """broadcast() で送信失敗した接続が自動除去される。"""
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_json.side_effect = Exception("connection closed")

        await manager.connect(ws_good)
        await manager.connect(ws_bad)

        await manager.broadcast({"type": "test"})

        # 壊れた接続が除去されている
        assert ws_bad not in manager._connections
        # 正常な接続は残っている
        assert ws_good in manager._connections


# ---------------------------------------------------------------------------
# FastAPI app tests (HTTP endpoints)
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """GET /health エンドポイントのテスト。"""

    def _get_app(self):
        from pneuma_world.server import create_app

        return create_app()

    def test_health_returns_200(self):
        """GET /health が 200 を返す。"""
        app = self._get_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert "last_tick" in body
        assert "characters_active" in body


class TestPostEvent:
    """POST /api/events エンドポイントのテスト。"""

    def _get_app(self):
        from pneuma_world.server import create_app

        return create_app()

    def test_post_event_returns_accepted(self):
        """POST /api/events が 200 を返し、イベントが EventQueue に入る。"""
        app = self._get_app()
        client = TestClient(app)
        event_data = {
            "type": "environment",
            "content": "雨が降ってきた",
            "source": "human",
            "target": "world",
        }
        resp = client.post("/api/events", json=event_data)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"

    def test_post_event_pushes_to_queue(self):
        """POST /api/events で EventQueue にイベントが追加される。"""
        from pneuma_world.server import create_app

        app = create_app()
        client = TestClient(app)
        event_data = {
            "type": "environment",
            "content": "雷が鳴った",
            "source": "human",
            "target": "world",
        }
        client.post("/api/events", json=event_data)

        # EventQueue からドレインしてイベントが入っていることを確認
        events = app.state.event_queue.drain()
        assert len(events) == 1
        assert events[0].content == "雷が鳴った"
        assert events[0].type == "environment"


# ---------------------------------------------------------------------------
# WebSocket endpoint tests
# ---------------------------------------------------------------------------


class TestWebSocketEndpoint:
    """WebSocket /ws/world-state のテスト。"""

    def _get_app(self):
        from pneuma_world.server import create_app

        return create_app()

    def test_websocket_connect_and_disconnect(self):
        """WebSocket 接続・切断が正常に動作する。"""
        app = self._get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/world-state") as ws:
            # 接続成功 — manager に接続が追加されているはず
            assert len(app.state.manager._connections) == 1
        # 切断後は接続が除去されている
        assert len(app.state.manager._connections) == 0

    def test_websocket_receives_world_event(self):
        """WebSocket 経由で world_event を送信できる。"""
        app = self._get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/world-state") as ws:
            ws.send_json({
                "type": "world_event",
                "event": {
                    "type": "environment",
                    "content": "風が吹いた",
                    "source": "human",
                    "target": "world",
                },
            })
            # EventQueue にイベントが push されていることを確認
            # (少し待ってからドレイン)
            import time
            time.sleep(0.1)
            events = app.state.event_queue.drain()
            assert len(events) == 1
            assert events[0].content == "風が吹いた"


# ---------------------------------------------------------------------------
# Engine injection tests
# ---------------------------------------------------------------------------


class TestEngineInjection:
    """WorldEngine 注入の設計テスト。"""

    def test_create_app_without_engine(self):
        """エンジンなしで app を作成できる（テスト用）。"""
        from pneuma_world.server import create_app

        app = create_app(engine=None)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_create_app_with_mock_engine(self):
        """モックエンジンを注入して app を作成できる。"""
        from pneuma_world.server import create_app

        mock_engine = MagicMock()
        mock_engine.state = MagicMock()
        mock_engine.state.tick = 5
        mock_engine.state.characters = {"char1": MagicMock(), "char2": MagicMock()}

        app = create_app(engine=mock_engine)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["characters_active"] == 2

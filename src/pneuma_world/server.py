"""FastAPI WebSocket server for pneuma-world.

WorldEngine をバックグラウンドタスクとして起動し、
WorldState をリアルタイム配信する WebSocket サーバー。
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from pneuma_world.events import EventQueue
from pneuma_world.models.event import WorldEvent

if TYPE_CHECKING:
    from pneuma_world.engine import WorldEngine


class ConnectionManager:
    """WebSocket 接続管理 + ブロードキャスト。"""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """WebSocket 接続を受け入れてリストに追加。"""
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """WebSocket 接続をリストから除去。"""
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, data: dict) -> None:
        """全接続に JSON データを送信。送信失敗した接続は自動除去。"""
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                self._connections.remove(ws)


def create_app(engine: WorldEngine | None = None) -> FastAPI:
    """FastAPI アプリケーションを作成する。

    Args:
        engine: WorldEngine インスタンス。None の場合はエンジンなしで起動
                （テスト用）。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # WorldEngine をバックグラウンドタスクとして起動
        task = None
        if app.state.engine is not None:
            task = asyncio.create_task(_engine_loop(app))
        yield
        # シャットダウン処理
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(lifespan=lifespan)

    # アプリケーション状態に保存
    app.state.engine = engine
    app.state.manager = ConnectionManager()
    app.state.event_queue = EventQueue()
    app.state.last_tick_time: datetime | None = None

    # ----- Routes -----

    @app.websocket("/ws/world-state")
    async def world_state_ws(websocket: WebSocket) -> None:
        mgr: ConnectionManager = app.state.manager
        await mgr.connect(websocket)
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "world_event":
                    event_data = data.get("event", {})
                    event = WorldEvent(
                        type=event_data.get("type", "environment"),
                        content=event_data.get("content", ""),
                        source=event_data.get("source", "human"),
                        target=event_data.get("target", "world"),
                    )
                    await app.state.event_queue.push(event)
        except WebSocketDisconnect:
            mgr.disconnect(websocket)

    @app.post("/api/events")
    async def post_event(event: dict) -> dict:
        """WorldEvent を EventQueue に push する。"""
        world_event = WorldEvent(
            type=event.get("type", "environment"),
            content=event.get("content", ""),
            source=event.get("source", "human"),
            target=event.get("target", "world"),
        )
        await app.state.event_queue.push(world_event)
        return {"status": "accepted", "event_id": world_event.id}

    @app.get("/health")
    async def health() -> dict:
        """ヘルスチェックエンドポイント。"""
        eng = app.state.engine
        if eng is not None:
            characters_active = len(eng.state.characters)
            last_tick = (
                app.state.last_tick_time.isoformat()
                if app.state.last_tick_time
                else None
            )
        else:
            characters_active = 0
            last_tick = None

        return {
            "status": "healthy",
            "last_tick": last_tick,
            "characters_active": characters_active,
        }

    return app


async def _engine_loop(app: FastAPI) -> None:
    """WorldEngine のメインループ。バックグラウンドタスクとして実行。"""
    engine: WorldEngine = app.state.engine
    mgr: ConnectionManager = app.state.manager

    while True:
        try:
            results = await engine.tick()
            app.state.last_tick_time = datetime.now()

            if results:
                # tick 完了時に WorldState をブロードキャスト
                state = engine.state
                state_data = {
                    "type": "world_state",
                    "tick": state.tick,
                    "world_time": state.world_time.isoformat(),
                    "characters": {
                        cid: {
                            "character_id": cs.character_id,
                            "location": cs.location,
                            "position": {"x": cs.position.x, "y": cs.position.y},
                            "activity": cs.activity,
                        }
                        for cid, cs in state.characters.items()
                    },
                }
                await mgr.broadcast(state_data)

            # visual tick interval (1秒)
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception:
            # エラーが発生してもループを継続
            await asyncio.sleep(1.0)

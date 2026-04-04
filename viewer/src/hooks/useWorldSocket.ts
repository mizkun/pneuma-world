import { useState, useEffect, useRef, useCallback } from 'react';
import { gameBridge } from '../bridge/GameBridge';

export interface ChatMessage {
  id: string;
  type: 'speech' | 'thought' | 'action' | 'system';
  characterName?: string;
  content: string;
  timestamp: string;
}

export interface WorldStatus {
  worldTime: string;
  characters: { name: string; state: string }[];
}

export type ConnectionState = 'connecting' | 'connected' | 'disconnected';

export function useWorldSocket(url: string = 'ws://localhost:8000/ws/world-state') {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<WorldStatus>({ worldTime: '--:--', characters: [] });
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef<number>(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    // 既に接続中なら何もしない
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    setConnectionState('connecting');
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setConnectionState('connected');
      reconnectCountRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'world_state':
            // Phaser に転送
            gameBridge.updateWorldState(data);
            // ステータスバー更新
            setStatus({
              worldTime: data.world_time || '--:--',
              characters: data.characters
                ? Object.values(data.characters as Record<string, any>).map((c: any) => ({
                    name: c.character_id || c.name || 'unknown',
                    state: c.activity || c.state || 'idle',
                  }))
                : [],
            });
            break;

          case 'speech':
            // 吹き出し表示
            gameBridge.showSpeech({ characterId: data.character_id, content: data.content });
            // チャットログ追加
            setMessages((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                type: 'speech',
                characterName: data.character_name,
                content: data.content,
                timestamp: data.timestamp || new Date().toISOString(),
              },
            ]);
            break;

          case 'thought':
            setMessages((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                type: 'thought',
                characterName: data.character_name,
                content: data.thought,
                timestamp: data.timestamp || new Date().toISOString(),
              },
            ]);
            break;

          case 'action_queue':
            gameBridge.updateActionQueue(data);
            break;
        }
      } catch {
        // JSON パースエラーは無視
      }
    };

    ws.onclose = () => {
      setConnectionState('disconnected');
      wsRef.current = null;
      // Exponential backoff 再接続 (1s -> 2s -> 4s -> ... -> 30s max)
      const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 30000);
      reconnectCountRef.current++;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [url]);

  /** 介入イベント送信 */
  const sendEvent = useCallback(
    (eventType: string, content: string, target: string = 'world') => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'world_event',
            event: {
              type: eventType,
              content,
              source: 'human',
              target,
            },
          }),
        );
      }
    },
    [],
  );

  useEffect(() => {
    connect();
    return () => {
      // クリーンアップ: 再接続タイマーを止め、WebSocket を閉じる
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  return { messages, status, connectionState, sendEvent };
}

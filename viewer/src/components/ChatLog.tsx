import { useEffect, useRef } from 'react';

export interface ChatMessage {
  id: string;
  type: 'speech' | 'thought' | 'action' | 'system';
  characterName?: string;
  content: string;
  timestamp: string;
}

const demoMessages: ChatMessage[] = [
  { id: '1', type: 'system', content: '放課後の部室。3人が集まっている。', timestamp: '15:30' },
  { id: '2', type: 'speech', characterName: '葵', content: 'ねぇねぇ、新しいフレームワーク見つけたんだけど！', timestamp: '15:31' },
  { id: '3', type: 'thought', characterName: '凛', content: 'また葵が何か見つけてきたか…', timestamp: '15:31' },
  { id: '4', type: 'speech', characterName: '凛', content: '…何のフレームワーク？', timestamp: '15:31' },
  { id: '5', type: 'speech', characterName: 'ひなた', content: 'えへへ、フレームワークって絵を描くやつ？', timestamp: '15:32' },
  { id: '6', type: 'action', characterName: '葵', content: 'PCの画面を見せる', timestamp: '15:32' },
];

function MessageItem({ message }: { message: ChatMessage }) {
  switch (message.type) {
    case 'system':
      return (
        <div className="text-center text-xs text-gray-500 py-1">
          <span className="text-gray-600 mr-1">{message.timestamp}</span>
          {message.content}
        </div>
      );

    case 'speech':
      return (
        <div className="py-1">
          <span className="text-gray-600 text-xs mr-1">{message.timestamp}</span>
          <span className="font-bold text-blue-300">{message.characterName}</span>
          <span className="text-gray-400 mx-1">:</span>
          <span className="text-gray-200">{message.content}</span>
        </div>
      );

    case 'thought':
      return (
        <div className="py-1 opacity-60">
          <span className="text-gray-600 text-xs mr-1">{message.timestamp}</span>
          <span className="font-bold text-purple-400">{message.characterName}</span>
          <span className="text-gray-400 mx-1">:</span>
          <span className="italic text-gray-400">{message.content}</span>
        </div>
      );

    case 'action':
      return (
        <div className="py-1">
          <span className="text-gray-600 text-xs mr-1">{message.timestamp}</span>
          <span className="text-gray-500">* {message.characterName} {message.content}</span>
        </div>
      );

    default:
      return null;
  }
}

interface ChatLogProps {
  messages?: ChatMessage[];
}

export function ChatLog({ messages }: ChatLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // WebSocket 未接続時はデモデータを fallback として使用
  const displayMessages = messages && messages.length > 0 ? messages : demoMessages;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [displayMessages]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-gray-800">
      <h2 className="text-lg font-bold px-4 pt-3 pb-2 text-gray-100 shrink-0">Chat Log</h2>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 pb-4 text-sm"
      >
        {displayMessages.map((msg) => (
          <MessageItem key={msg.id} message={msg} />
        ))}
      </div>
    </div>
  );
}

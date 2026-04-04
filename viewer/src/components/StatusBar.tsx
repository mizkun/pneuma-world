import type { WorldStatus, ConnectionState } from '../hooks/useWorldSocket';

interface CharacterStatus {
  name: string;
  status: string;
}

const demoTime = '15:32';

const demoCharacterStatuses: CharacterStatus[] = [
  { name: '葵', status: '読書中' },
  { name: '凛', status: '会話中' },
  { name: 'ひなた', status: 'idle' },
];

const connectionIndicator: Record<ConnectionState, { emoji: string; label: string }> = {
  connected: { emoji: '\u{1F7E2}', label: 'Connected' },
  connecting: { emoji: '\u{1F7E1}', label: 'Connecting...' },
  disconnected: { emoji: '\u{1F534}', label: 'Disconnected' },
};

interface StatusBarProps {
  status?: WorldStatus;
  connectionState?: ConnectionState;
}

export function StatusBar({ status, connectionState = 'disconnected' }: StatusBarProps) {
  const indicator = connectionIndicator[connectionState];

  // WebSocket 未接続時はデモデータを fallback として使用
  const hasLiveData = status && status.characters.length > 0;
  const displayTime = hasLiveData ? status.worldTime : demoTime;
  const displayCharacters: CharacterStatus[] = hasLiveData
    ? status.characters.map((c) => ({ name: c.name, status: c.state }))
    : demoCharacterStatuses;

  return (
    <div className="h-12 flex items-center px-4 bg-gray-700 text-gray-200 border-b border-gray-600 shrink-0 gap-3">
      <span className="text-sm" title={indicator.label}>
        {indicator.emoji}
      </span>
      <span className="font-mono text-sm font-bold">{displayTime}</span>
      <span className="text-gray-500">|</span>
      {displayCharacters.map((char, i) => (
        <span key={char.name} className="text-sm flex items-center gap-1">
          <span className="font-bold text-blue-300">{char.name}</span>
          <span className="text-gray-400">:</span>
          <span className="text-gray-300">{char.status}</span>
          {i < displayCharacters.length - 1 && (
            <span className="text-gray-500 ml-2">|</span>
          )}
        </span>
      ))}
    </div>
  );
}

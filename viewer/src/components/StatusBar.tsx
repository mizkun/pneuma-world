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

export function StatusBar() {
  return (
    <div className="h-12 flex items-center px-4 bg-gray-700 text-gray-200 border-b border-gray-600 shrink-0 gap-3">
      <span className="font-mono text-sm font-bold">{demoTime}</span>
      <span className="text-gray-500">|</span>
      {demoCharacterStatuses.map((char, i) => (
        <span key={char.name} className="text-sm flex items-center gap-1">
          <span className="font-bold text-blue-300">{char.name}</span>
          <span className="text-gray-400">:</span>
          <span className="text-gray-300">{char.status}</span>
          {i < demoCharacterStatuses.length - 1 && (
            <span className="text-gray-500 ml-2">|</span>
          )}
        </span>
      ))}
    </div>
  );
}

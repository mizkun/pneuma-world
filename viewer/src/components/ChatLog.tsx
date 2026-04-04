export function ChatLog() {
  return (
    <div className="flex-1 overflow-y-auto p-4 bg-gray-800 text-gray-300">
      <h2 className="text-lg font-bold mb-2 text-gray-100">Chat Log</h2>
      <div className="space-y-2">
        <p className="text-sm text-gray-500">-- no messages yet --</p>
      </div>
    </div>
  );
}

import { WorldMap } from './components/WorldMap'
import { ChatLog } from './components/ChatLog'
import { StatusBar } from './components/StatusBar'
import { useWorldSocket } from './hooks/useWorldSocket'

function App() {
  const { messages, status, connectionState } = useWorldSocket()

  return (
    <div className="w-[1920px] h-[1080px] mx-auto flex bg-gray-900">
      {/* Left: Phaser Canvas (60% = 1152px) */}
      <div className="w-[1152px] h-full flex items-center justify-center bg-black">
        <WorldMap />
      </div>

      {/* Right: React UI (40% = 768px) */}
      <div className="w-[768px] h-full flex flex-col">
        <StatusBar status={status} connectionState={connectionState} />
        <ChatLog messages={messages} />
      </div>
    </div>
  )
}

export default App

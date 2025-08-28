import { useState, useCallback, useEffect } from 'react'
import {
  BarVisualizer,
  DisconnectButton,
  RoomAudioRenderer,
  RoomContext,
  VideoTrack,
  VoiceAssistantControlBar,
  useVoiceAssistant,
} from '@livekit/components-react'
import { AnimatePresence, motion } from 'framer-motion'
import { Room, RoomEvent } from 'livekit-client'
import { MicrophoneIcon, VideoCameraIcon, PhoneXMarkIcon } from '@heroicons/react/24/solid'
import { ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline'

type ConnectionDetails = {
  serverUrl: string
  roomName: string
  participantName: string
  participantToken: string
}

export default function LiveKitChat() {
  const [room] = useState(new Room())
  const [isConnected, setIsConnected] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState('')
  const [password, setPassword] = useState('')
  const [showPasswordInput, setShowPasswordInput] = useState(true)

  const onConnectButtonClicked = useCallback(async () => {
    setError('')
    setIsConnecting(true)
    
    try {
      // Call your backend to get connection details
      // This should match your LiveKit server configuration
      const response = await fetch('/api/livekit/connection-details', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ password })
      })
      
      if (!response.ok) {
        if (response.status === 401) {
          setError('Invalid password')
        } else {
          setError('Connection failed')
        }
        setIsConnecting(false)
        return
      }
      
      const connectionDetails: ConnectionDetails = await response.json()
      
      await room.connect(connectionDetails.serverUrl, connectionDetails.participantToken)
      await room.localParticipant.setMicrophoneEnabled(true)
      setIsConnected(true)
      setShowPasswordInput(false)
      setIsConnecting(false)
    } catch (err) {
      console.error('Connection error:', err)
      setError('Failed to connect to LiveKit')
      setIsConnecting(false)
    }
  }, [room, password])

  const onDisconnect = useCallback(async () => {
    await room.disconnect()
    setIsConnected(false)
    setShowPasswordInput(true)
  }, [room])

  useEffect(() => {
    const onDeviceFailure = (error: Error) => {
      console.error(error)
      alert('Error acquiring camera or microphone permissions. Please grant the necessary permissions and reload.')
    }

    room.on(RoomEvent.MediaDevicesError, onDeviceFailure)
    
    return () => {
      room.off(RoomEvent.MediaDevicesError, onDeviceFailure)
    }
  }, [room])

  return (
    <div className="h-full bg-white dark:bg-gray-800 p-8">
      <div className="max-w-4xl mx-auto h-full flex flex-col">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <ChatBubbleLeftRightIcon className="w-8 h-8 text-blue-600 dark:text-blue-400" />
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Live Voice Chat</h1>
          </div>
          <p className="text-gray-600 dark:text-gray-400">
            Connect with an AI assistant for real-time voice conversations
          </p>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col">
          <RoomContext.Provider value={room}>
            <AnimatePresence mode="wait">
              {!isConnected && showPasswordInput ? (
                <motion.div
                  key="connect"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3 }}
                  className="flex-1 flex items-center justify-center"
                >
                  <div className="bg-gray-50 dark:bg-gray-700 rounded-xl p-8 max-w-md w-full">
                    <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6 text-center">
                      Start a Voice Conversation
                    </h2>
                    
                    {/* Password Input */}
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Access Password
                      </label>
                      <input
                        type="password"
                        placeholder="Enter password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onKeyPress={(e) => {
                          if (e.key === 'Enter' && !isConnecting) {
                            onConnectButtonClicked()
                          }
                        }}
                        disabled={isConnecting}
                        className="w-full px-4 py-2 bg-white dark:bg-gray-600 border border-gray-300 dark:border-gray-500 text-gray-900 dark:text-white rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                      />
                    </div>

                    {/* Error Message */}
                    {error && (
                      <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                      </div>
                    )}

                    {/* Connect Button */}
                    <button
                      onClick={onConnectButtonClicked}
                      disabled={isConnecting || !password}
                      className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <MicrophoneIcon className="w-5 h-5" />
                      {isConnecting ? 'Connecting...' : 'Start Voice Chat'}
                    </button>

                    {/* Info Text */}
                    <p className="mt-4 text-xs text-gray-500 dark:text-gray-400 text-center">
                      Microphone access will be requested after connecting
                    </p>
                  </div>
                </motion.div>
              ) : isConnected ? (
                <motion.div
                  key="connected"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.3 }}
                  className="flex-1 flex flex-col"
                >
                  <VoiceAssistantContent onDisconnect={onDisconnect} />
                </motion.div>
              ) : null}
            </AnimatePresence>
          </RoomContext.Provider>
        </div>
      </div>
    </div>
  )
}

function VoiceAssistantContent({ onDisconnect }: { onDisconnect: () => void }) {
  const { state: agentState, videoTrack, audioTrack } = useVoiceAssistant()
  
  return (
    <div className="flex flex-col h-full">
      {/* Status Bar */}
      <div className="mb-4 px-4 py-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span className="text-sm font-medium text-green-700 dark:text-green-400">
              Connected
            </span>
            {agentState && agentState !== 'disconnected' && (
              <span className="text-sm text-gray-600 dark:text-gray-400">
                • {agentState === 'listening' ? 'Listening' : 
                   agentState === 'thinking' ? 'Thinking' : 
                   agentState === 'speaking' ? 'Speaking' : agentState}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Visualizer */}
      <div className="flex-1 flex items-center justify-center">
        {videoTrack ? (
          <div className="w-full max-w-2xl aspect-video rounded-xl overflow-hidden bg-gray-100 dark:bg-gray-700">
            <VideoTrack trackRef={videoTrack} className="w-full h-full object-cover" />
          </div>
        ) : (
          <div className="w-full max-w-2xl">
            <BarVisualizer
              state={agentState}
              barCount={7}
              trackRef={audioTrack}
              className="agent-visualizer"
              options={{ 
                minHeight: 40,
                maxHeight: 150,
                accentColor: 'rgb(59, 130, 246)', // blue-500
                accentColorSecondary: 'rgb(147, 197, 253)', // blue-300
              }}
            />
            
            {/* State Indicator */}
            <div className="text-center mt-8">
              <p className="text-lg font-medium text-gray-700 dark:text-gray-300">
                {agentState === 'listening' ? '🎤 Listening...' :
                 agentState === 'thinking' ? '💭 Processing...' :
                 agentState === 'speaking' ? '🔊 Speaking...' :
                 agentState === 'connecting' ? '🔄 Connecting...' :
                 'Ready to chat'}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Control Bar */}
      <div className="mt-6 flex justify-center gap-4">
        <VoiceAssistantControlBar 
          controls={{ 
            leave: false,
            microphone: true,
            screenShare: false,
            camera: false,
            chat: false,
          }} 
        />
        
        <button
          onClick={onDisconnect}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
        >
          <PhoneXMarkIcon className="w-5 h-5" />
          End Call
        </button>
      </div>

      {/* Audio Renderer */}
      <RoomAudioRenderer />
    </div>
  )
}
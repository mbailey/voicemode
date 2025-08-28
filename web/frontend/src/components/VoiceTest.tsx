import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { testVoice } from '../api/client'
import { MicrophoneIcon } from '@heroicons/react/24/solid'

export default function VoiceTest() {
  const [text, setText] = useState('Hello! This is a test of the Voice Mode text-to-speech system.')
  const [responseDuration, setResponseDuration] = useState<number>(120)
  const [useResponseDuration, setUseResponseDuration] = useState(false)
  const [selectedVoice, setSelectedVoice] = useState<string>('')
  const [logs, setLogs] = useState<string[]>([])

  // Available voices - you can expand this list
  const voices = [
    { value: '', label: 'Default Voice' },
    // OpenAI voices
    { value: 'alloy', label: 'Alloy (OpenAI)' },
    { value: 'echo', label: 'Echo (OpenAI)' },
    { value: 'fable', label: 'Fable (OpenAI)' },
    { value: 'nova', label: 'Nova (OpenAI)' },
    { value: 'onyx', label: 'Onyx (OpenAI)' },
    { value: 'shimmer', label: 'Shimmer (OpenAI)' },
    // Kokoro voices
    { value: 'af_sky', label: 'Sky (Kokoro Female)' },
    { value: 'af_sarah', label: 'Sarah (Kokoro Female)' },
    { value: 'am_adam', label: 'Adam (Kokoro Male)' },
    { value: 'af_nicole', label: 'Nicole (Kokoro Female)' },
    { value: 'bf_emma', label: 'Emma (British Female)' },
    { value: 'bm_george', label: 'George (British Male)' },
  ]

  const speakMutation = useMutation({
    mutationFn: async () => {
      setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Starting TTS...`])
      const params = {
        text,
        ...(useResponseDuration && { response_duration: responseDuration }),
        ...(selectedVoice && { voice: selectedVoice })
      }
      const result = await testVoice(params)
      
      // Add the actual output from the voice command
      if (result.success) {
        if (result.stderr) {
          // Parse stderr logs (these are the detailed logs)
          const lines = result.stderr.split('\n').filter(line => line.trim())
          lines.forEach(line => {
            setLogs(prev => [...prev, line])
          })
        }
        if (result.stdout) {
          // Parse the stdout to highlight what was spoken and heard
          const output = result.stdout.trim()
          if (output.includes('📢 Spoke:') && output.includes('🎤 Heard:')) {
            // Format the conversation output specially
            setLogs(prev => [...prev, '', '=== Conversation ==='])
            const spokePart = output.match(/📢 Spoke: (.*?) 🎤/)
            const heardPart = output.match(/🎤 Heard: (.*?) ⏱️/)
            const timingPart = output.match(/⏱️ Timing: (.*)/)
            
            if (spokePart) {
              setLogs(prev => [...prev, `📢 Spoke: ${spokePart[1]}`])
            }
            if (heardPart) {
              setLogs(prev => [...prev, `🎤 Heard: ${heardPart[1]}`])
            }
            if (timingPart) {
              setLogs(prev => [...prev, `⏱️ ${timingPart[1]}`])
            }
          } else {
            setLogs(prev => [...prev, '', output])
          }
        }
      } else {
        setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Error: ${result.error || 'Unknown error'}`])
      }
      
      return result
    },
    onError: (error) => {
      setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Error: ${error}`])
    }
  })

  const handleSpeak = () => {
    setLogs([]) // Clear previous logs
    speakMutation.mutate()
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Voice Testing</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">Test and configure text-to-speech settings</p>
      </div>

      {/* Text Input */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Text to Speak
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Enter text to speak..."
        />
      </div>

      {/* Voice Selection */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Voice
        </label>
        <select
          value={selectedVoice}
          onChange={(e) => setSelectedVoice(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {voices.map(voice => (
            <option key={voice.value} value={voice.value}>
              {voice.label}
            </option>
          ))}
        </select>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          Select a voice for text-to-speech. Leave as "Default Voice" to use your configured default.
        </p>
      </div>

      {/* Response Duration Option */}
      <div className="mb-6 bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
        <div className="flex items-center mb-3">
          <input
            type="checkbox"
            id="useResponseDuration"
            checked={useResponseDuration}
            onChange={(e) => setUseResponseDuration(e.target.checked)}
            className="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
          />
          <label htmlFor="useResponseDuration" className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
            Wait for response after speaking
          </label>
        </div>
        
        {useResponseDuration && (
          <div className="ml-6">
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-2">
              Response Duration: {responseDuration} seconds
            </label>
            <input
              type="range"
              min="5"
              max="300"
              step="5"
              value={responseDuration}
              onChange={(e) => setResponseDuration(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>5s</span>
              <span>1m</span>
              <span>2m</span>
              <span>3m</span>
              <span>5m</span>
            </div>
          </div>
        )}
      </div>

      {/* Speak Button */}
      <div className="mb-8">
        <button
          onClick={handleSpeak}
          disabled={!text.trim() || speakMutation.isPending}
          className="flex items-center px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <MicrophoneIcon className="w-5 h-5 mr-2" />
          {speakMutation.isPending ? 'Speaking...' : 'Speak'}
        </button>
      </div>

      {/* Logs Output */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-2">Logs</h3>
        <div className="font-mono text-sm text-gray-300 space-y-1 max-h-96 overflow-y-auto">
          {logs.length === 0 ? (
            <div className="text-gray-500">No logs yet. Click Speak to test voice output.</div>
          ) : (
            logs.map((log, index) => {
              // Special formatting for conversation sections
              if (log === '=== Conversation ===') {
                return (
                  <div key={index} className="text-blue-400 font-bold mt-2 mb-1">
                    {log}
                  </div>
                )
              }
              
              // Special formatting for spoke/heard/timing
              if (log.startsWith('📢 Spoke:')) {
                return (
                  <div key={index} className="text-cyan-400 ml-2">
                    {log}
                  </div>
                )
              }
              if (log.startsWith('🎤 Heard:')) {
                return (
                  <div key={index} className="text-yellow-400 ml-2 font-semibold">
                    {log}
                  </div>
                )
              }
              if (log.startsWith('⏱️')) {
                return (
                  <div key={index} className="text-gray-500 text-xs ml-2 mt-1">
                    {log}
                  </div>
                )
              }
              
              // Highlight success messages in green
              const isSuccess = log.includes('✓') || log.includes('successfully')
              // Highlight errors in red (but not ERROR log level)
              const isError = log.includes('Error:') && !log.includes('-ERROR-')
              // Warning for ERROR log level (the aiohttp warnings)
              const isWarning = log.includes('-ERROR-')
              
              // Parse log format
              const logParts = log.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})-(\w+)-(.*)$/)
              
              if (logParts) {
                const timestamp = logParts[1]
                const level = logParts[2]
                const message = logParts[3]
                
                return (
                  <div key={index} className="flex">
                    <span className="text-gray-600 text-xs">{timestamp}</span>
                    <span className="text-gray-500 mx-1">-</span>
                    <span className={
                      level === 'ERROR' ? 'text-orange-400 text-xs' : 
                      level === 'INFO' ? 'text-blue-400 text-xs' : 
                      'text-gray-400 text-xs'
                    }>{level}</span>
                    <span className="text-gray-500 mx-1">-</span>
                    <span className={
                      isSuccess ? 'text-green-400' : 
                      isWarning ? 'text-orange-400 text-xs' :
                      isError ? 'text-red-400' : 
                      'text-gray-300'
                    }>
                      {message}
                    </span>
                  </div>
                )
              }
              
              return (
                <div 
                  key={index} 
                  className={
                    isSuccess ? 'text-green-400' : 
                    isError ? 'text-red-400' : 
                    'text-gray-300'
                  }
                >
                  {log}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
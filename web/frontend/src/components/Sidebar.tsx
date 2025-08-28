import { 
  HomeIcon, 
  CpuChipIcon, 
  ChatBubbleLeftRightIcon, 
  Cog6ToothIcon,
  MicrophoneIcon,
  SpeakerWaveIcon,
  BeakerIcon,
  VideoCameraIcon
} from '@heroicons/react/24/outline'

type View = 'dashboard' | 'whisper' | 'kokoro' | 'conversations' | 'voice-test' | 'live-chat' | 'settings'

interface SidebarProps {
  currentView: View
  onNavigate: (view: View) => void
}

export default function Sidebar({ currentView, onNavigate }: SidebarProps) {
  const navigation = [
    { name: 'Dashboard', id: 'dashboard' as View, icon: HomeIcon },
    { name: 'Services', id: null, icon: null, isHeader: true },
    { name: 'Whisper STT', id: 'whisper' as View, icon: MicrophoneIcon, indent: true },
    { name: 'Kokoro TTS', id: 'kokoro' as View, icon: SpeakerWaveIcon, indent: true },
    { name: 'Conversations', id: 'conversations' as View, icon: ChatBubbleLeftRightIcon },
    { name: 'Live Chat', id: 'live-chat' as View, icon: VideoCameraIcon },
    { name: 'Voice Testing', id: 'voice-test' as View, icon: BeakerIcon },
    { name: 'Settings', id: 'settings' as View, icon: Cog6ToothIcon },
  ]

  return (
    <div className="flex flex-col w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
      {/* Logo/Title */}
      <div className="flex items-center h-16 px-4 border-b border-gray-200 dark:border-gray-700">
        <CpuChipIcon className="w-8 h-8 text-blue-600 dark:text-blue-400 mr-2" />
        <span className="text-xl font-bold text-gray-900 dark:text-white">Voice Mode</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item, index) => {
          if (item.isHeader) {
            return (
              <div key={index} className="px-3 pt-4 pb-2">
                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {item.name}
                </p>
              </div>
            )
          }

          const Icon = item.icon
          const isActive = currentView === item.id
          
          return (
            <button
              key={item.id}
              onClick={() => item.id && onNavigate(item.id)}
              className={`
                w-full flex items-center px-3 py-2 text-sm font-medium rounded-md
                transition-colors duration-150
                ${item.indent ? 'ml-6' : ''}
                ${isActive 
                  ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200' 
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                }
              `}
            >
              {Icon && <Icon className="mr-3 h-5 w-5" />}
              {item.name}
            </button>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="flex-shrink-0 px-4 py-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center">
          <div className="w-2 h-2 bg-green-400 rounded-full mr-2 animate-pulse"></div>
          <span className="text-sm text-gray-600 dark:text-gray-400">System Online</span>
        </div>
      </div>
    </div>
  )
}
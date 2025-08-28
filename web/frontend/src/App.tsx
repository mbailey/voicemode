import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Dashboard from './components/Dashboard'
import Sidebar from './components/Sidebar'
import ServiceDetail from './components/ServiceDetail'
import Conversations from './components/Conversations'
import VoiceTest from './components/VoiceTest'
import LiveKitChat from './components/LiveKitChat'
import './App.css'

const queryClient = new QueryClient()

type View = 'dashboard' | 'whisper' | 'kokoro' | 'conversations' | 'voice-test' | 'live-chat' | 'settings'

function App() {
  const [currentView, setCurrentView] = useState<View>('dashboard')

  const renderContent = () => {
    switch(currentView) {
      case 'dashboard':
        return <Dashboard />
      case 'whisper':
        return <ServiceDetail serviceName="whisper" />
      case 'kokoro':
        return <ServiceDetail serviceName="kokoro" />
      case 'conversations':
        return <Conversations />
      case 'voice-test':
        return <VoiceTest />
      case 'live-chat':
        return <LiveKitChat />
      case 'settings':
        return <div className="p-8"><h2 className="text-2xl font-bold">Settings</h2></div>
      default:
        return <Dashboard />
    }
  }

  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex h-screen bg-gray-100 dark:bg-gray-900">
        {/* Sidebar */}
        <Sidebar currentView={currentView} onNavigate={setCurrentView} />
        
        {/* Main Content */}
        <main className="flex-1 overflow-y-auto">
          {renderContent()}
        </main>
      </div>
    </QueryClientProvider>
  )
}

export default App
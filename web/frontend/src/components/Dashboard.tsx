import { useQuery } from '@tanstack/react-query'
import ServiceCard from './ServiceCard'
import StatsCard from './StatsCard'
import { fetchServices, fetchVoiceStats } from '../api/client'

export default function Dashboard() {
  const { data: services, isLoading: servicesLoading } = useQuery({
    queryKey: ['services'],
    queryFn: fetchServices,
    refetchInterval: 5000 // Refresh every 5 seconds
  })

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['voice-stats'],
    queryFn: fetchVoiceStats,
    refetchInterval: 10000
  })

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">Monitor and control Voice Mode services</p>
      </div>

      {/* Service Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {servicesLoading ? (
          <div className="text-gray-500">Loading services...</div>
        ) : (
          services?.services.map((service: any) => (
            <ServiceCard key={service.name} service={service} />
          ))
        )}
      </div>

      {/* Stats Section */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Voice Statistics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {statsLoading ? (
            <div className="text-gray-500">Loading statistics...</div>
          ) : stats ? (
            <>
              <StatsCard 
                title="Total Conversations" 
                value={stats.session.total_interactions.toString()}
                subtitle="This session"
              />
              <StatsCard 
                title="Success Rate" 
                value={`${(stats.session.success_rate * 100).toFixed(1)}%`}
                subtitle="Voice recognition"
              />
              <StatsCard 
                title="Avg Response Time" 
                value={`${stats.performance.avg_ttfa_ms}ms`}
                subtitle="Time to first audio"
              />
              <StatsCard 
                title="Session Duration" 
                value={`${Math.floor(stats.session.duration_seconds / 60)}min`}
                subtitle="Current session"
              />
            </>
          ) : null}
        </div>
      </div>

      {/* Recent Activity */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Recent Activity</h2>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <div className="space-y-2">
            <ActivityItem time="2 min ago" message="Whisper processed voice input" type="info" />
            <ActivityItem time="5 min ago" message="Kokoro generated TTS response" type="info" />
            <ActivityItem time="10 min ago" message="Service health check completed" type="success" />
          </div>
        </div>
      </div>
    </div>
  )
}

function ActivityItem({ time, message, type }: { time: string, message: string, type: string }) {
  const typeColors = {
    info: 'text-blue-600 dark:text-blue-400',
    success: 'text-green-600 dark:text-green-400',
    warning: 'text-yellow-600 dark:text-yellow-400',
    error: 'text-red-600 dark:text-red-400'
  }

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <div className="flex items-center">
        <div className={`w-2 h-2 rounded-full mr-3 ${type === 'success' ? 'bg-green-400' : 'bg-blue-400'}`}></div>
        <span className="text-sm text-gray-700 dark:text-gray-300">{message}</span>
      </div>
      <span className="text-xs text-gray-500 dark:text-gray-400">{time}</span>
    </div>
  )
}
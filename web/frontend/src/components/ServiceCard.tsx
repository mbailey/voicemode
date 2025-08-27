import { PlayIcon, StopIcon, ArrowPathIcon } from '@heroicons/react/24/solid'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { startService, stopService, restartService } from '../api/client'

interface ServiceCardProps {
  service: {
    name: string
    display_name: string
    description: string
    status: string
    port: number
    cpu_usage: number
    memory_mb: number
  }
}

export default function ServiceCard({ service }: ServiceCardProps) {
  const queryClient = useQueryClient()
  
  const startMutation = useMutation({
    mutationFn: () => startService(service.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] })
    }
  })

  const stopMutation = useMutation({
    mutationFn: () => stopService(service.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] })
    }
  })

  const restartMutation = useMutation({
    mutationFn: () => restartService(service.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] })
    }
  })

  const isRunning = service.status === 'running'
  const statusColor = isRunning ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
  const statusDotColor = isRunning ? 'bg-green-400' : 'bg-gray-400'

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{service.display_name}</h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">{service.description}</p>
        </div>
        <div className={`px-2 py-1 rounded-full text-xs font-medium ${statusColor} dark:${statusColor}`}>
          <div className="flex items-center">
            <div className={`w-2 h-2 rounded-full mr-1 ${statusDotColor} ${isRunning ? 'animate-pulse' : ''}`}></div>
            {service.status}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Port</p>
          <p className="text-sm font-medium text-gray-900 dark:text-white">{service.port}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Memory</p>
          <p className="text-sm font-medium text-gray-900 dark:text-white">{service.memory_mb} MB</p>
        </div>
      </div>

      {/* CPU Usage Bar */}
      {isRunning && (
        <div className="mb-4">
          <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>CPU Usage</span>
            <span>{service.cpu_usage.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div 
              className="bg-blue-600 h-2 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(service.cpu_usage, 100)}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-2">
        {!isRunning ? (
          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="flex-1 flex items-center justify-center px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
          >
            <PlayIcon className="w-4 h-4 mr-1" />
            Start
          </button>
        ) : (
          <>
            <button
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
              className="flex-1 flex items-center justify-center px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
            >
              <StopIcon className="w-4 h-4 mr-1" />
              Stop
            </button>
            <button
              onClick={() => restartMutation.mutate()}
              disabled={restartMutation.isPending}
              className="flex-1 flex items-center justify-center px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
            >
              <ArrowPathIcon className="w-4 h-4 mr-1" />
              Restart
            </button>
          </>
        )}
      </div>
    </div>
  )
}
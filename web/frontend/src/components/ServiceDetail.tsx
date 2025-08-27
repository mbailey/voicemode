import { useQuery } from '@tanstack/react-query'
import { fetchServiceDetail } from '../api/client'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'

interface ServiceDetailProps {
  serviceName: string
}

export default function ServiceDetail({ serviceName }: ServiceDetailProps) {
  const { data: service, isLoading } = useQuery({
    queryKey: ['service', serviceName],
    queryFn: () => fetchServiceDetail(serviceName),
    refetchInterval: 5000
  })

  if (isLoading) {
    return <div className="p-8">Loading service details...</div>
  }

  if (!service) {
    return <div className="p-8">Service not found</div>
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{service.display_name}</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">{service.description}</p>
      </div>

      {/* Status and Configuration */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Status Card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Status</h2>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Status</span>
              <span className={`font-medium ${service.status === 'running' ? 'text-green-600' : 'text-gray-600'}`}>
                {service.status}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Port</span>
              <span className="font-medium text-gray-900 dark:text-white">{service.port}</span>
            </div>
          </div>
        </div>

        {/* Configuration Card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Configuration</h2>
          <div className="space-y-3">
            {service.configuration && Object.entries(service.configuration).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">{key}</span>
                <span className="font-medium text-gray-900 dark:text-white">
                  {Array.isArray(value) ? value.join(', ') : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Logs */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Recent Logs</h2>
        <div className="bg-gray-50 dark:bg-gray-900 rounded p-4 font-mono text-sm max-h-96 overflow-y-auto">
          {service.logs && service.logs.map((log: any, index: number) => (
            <div key={index} className="mb-2">
              <span className="text-gray-500 dark:text-gray-400">{log.timestamp}</span>
              <span className={`ml-2 ${log.level === 'error' ? 'text-red-600' : 'text-gray-700 dark:text-gray-300'}`}>
                [{log.level}] {log.message}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
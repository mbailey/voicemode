import axios from 'axios'

const API_BASE_URL = 'http://localhost:8080/api'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Service Management
export const fetchServices = async () => {
  const response = await apiClient.get('/services')
  return response.data
}

export const fetchServiceDetail = async (serviceName: string) => {
  const response = await apiClient.get(`/services/${serviceName}`)
  return response.data
}

export const startService = async (serviceName: string) => {
  const response = await apiClient.post(`/services/${serviceName}/start`)
  return response.data
}

export const stopService = async (serviceName: string) => {
  const response = await apiClient.post(`/services/${serviceName}/stop`)
  return response.data
}

export const restartService = async (serviceName: string) => {
  const response = await apiClient.post(`/services/${serviceName}/restart`)
  return response.data
}

// Statistics
export const fetchVoiceStats = async () => {
  const response = await apiClient.get('/stats/voice')
  return response.data
}

// Conversations
export const fetchCurrentConversation = async () => {
  const response = await apiClient.get('/conversations/current')
  return response.data
}

export const sendMessage = async (message: { content: string }) => {
  const response = await apiClient.post('/conversations/send', message)
  return response.data
}

// Health Check
export const fetchHealthStatus = async () => {
  const response = await apiClient.get('/health')
  return response.data
}

// Voice Testing
export const testVoice = async (params: { text: string, response_duration?: number, voice?: string }) => {
  const response = await apiClient.post('/voice/test', params)
  return response.data
}

export default apiClient
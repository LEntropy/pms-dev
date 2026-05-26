import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'

const api: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const auth = useAuthStore()
    if (error.response?.status === 401 && auth.refreshToken) {
      try {
        await auth.refresh()
        error.config.headers.Authorization = `Bearer ${auth.accessToken}`
        return api.request(error.config)
      } catch {
        auth.logout()
      }
    }
    return Promise.reject(error)
  },
)

export default api

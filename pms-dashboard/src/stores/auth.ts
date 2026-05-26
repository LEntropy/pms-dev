import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

interface User {
  id: string
  email: string
  display_name: string | null
  role: string
  organization_id: string | null
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('pms_access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('pms_refresh_token'))
  const user = ref<User | null>(null)

  const isAuthenticated = computed(() => !!accessToken.value)

  async function login(email: string, password: string) {
    const resp = await axios.post('/api/v1/auth/login', { email, password })
    accessToken.value = resp.data.access_token
    refreshToken.value = resp.data.refresh_token
    localStorage.setItem('pms_access_token', resp.data.access_token)
    localStorage.setItem('pms_refresh_token', resp.data.refresh_token)
    await fetchMe()
  }

  async function refresh() {
    const resp = await axios.post('/api/v1/auth/refresh', {
      refresh_token: refreshToken.value,
    })
    accessToken.value = resp.data.access_token
    refreshToken.value = resp.data.refresh_token
    localStorage.setItem('pms_access_token', resp.data.access_token)
    localStorage.setItem('pms_refresh_token', resp.data.refresh_token)
  }

  async function fetchMe() {
    const resp = await axios.get('/api/v1/auth/me', {
      headers: { Authorization: `Bearer ${accessToken.value}` },
    })
    user.value = resp.data
  }

  function logout() {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('pms_access_token')
    localStorage.removeItem('pms_refresh_token')
  }

  return { accessToken, refreshToken, user, isAuthenticated, login, refresh, fetchMe, logout }
})

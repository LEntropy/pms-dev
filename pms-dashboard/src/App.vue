<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-layout v-if="auth.isAuthenticated" style="min-height: 100vh">
      <n-layout-header bordered style="padding: 0 24px; display: flex; align-items: center; justify-content: space-between; height: 56px">
        <span style="font-size: 18px; font-weight: 600">PMS 관리 콘솔</span>
        <n-button text @click="handleLogout">로그아웃 ({{ auth.user?.email }})</n-button>
      </n-layout-header>
      <n-layout has-sider>
        <n-layout-sider bordered :width="200" style="padding: 16px 0">
          <n-menu :options="menuOptions" :value="currentRoute" @update:value="navigate" />
        </n-layout-sider>
        <n-layout-content style="padding: 24px">
          <router-view />
        </n-layout-content>
      </n-layout>
    </n-layout>
    <router-view v-else />
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const currentRoute = computed(() => route.path)

const menuOptions = [
  { label: '대시보드', key: '/dashboard' },
  { label: '엔드포인트', key: '/endpoints' },
  { label: '패치 카탈로그', key: '/patches' },
  { label: '정책', key: '/policies' },
  { label: '배포', key: '/deployments' },
  { label: '리포트', key: '/reports' },
  { label: '감사 로그', key: '/audit' },
  { label: '시스템 관리', key: '/admin' },
]

function navigate(key: string) {
  router.push(key)
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

const themeOverrides = {
  common: {
    primaryColor: '#1890ff',
    primaryColorHover: '#40a9ff',
  },
}
</script>

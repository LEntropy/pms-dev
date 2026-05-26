<template>
  <div class="login-container">
    <n-card title="PMS 관리자 로그인" style="max-width: 400px; margin: 0 auto; margin-top: 15vh">
      <n-form @submit.prevent="handleLogin">
        <n-form-item label="이메일">
          <n-input v-model:value="email" type="email" placeholder="admin@company.com" />
        </n-form-item>
        <n-form-item label="비밀번호">
          <n-input v-model:value="password" type="password" placeholder="비밀번호" />
        </n-form-item>
        <n-alert v-if="error" type="error" :title="error" style="margin-bottom: 16px" />
        <n-button type="primary" attr-type="submit" block :loading="loading">
          로그인
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(email.value, password.value)
    router.push('/dashboard')
  } catch (e: any) {
    error.value = e.response?.data?.detail || '로그인에 실패했습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  background: #f0f2f5;
  padding: 20px;
}
</style>

<template>
  <div>
    <div style="display: flex; justify-content: flex-end; margin-bottom: 16px">
      <n-button type="primary" @click="showCreate = true">정책 추가</n-button>
    </div>

    <n-data-table :columns="columns" :data="policies" :loading="loading" />

    <!-- 정책 생성 모달 -->
    <n-modal v-model:show="showCreate" title="정책 생성" preset="card" style="width: 600px">
      <n-form :model="form" label-placement="left" label-width="120">
        <n-form-item label="정책 이름">
          <n-input v-model:value="form.name" />
        </n-form-item>
        <n-form-item label="우선순위">
          <n-input-number v-model:value="form.priority" :min="1" :max="999" style="width:100%" />
        </n-form-item>
        <n-form-item label="대상 유형">
          <n-select v-model:value="form.target_type" :options="targetTypeOptions" />
        </n-form-item>
        <n-form-item label="대상 ID">
          <n-input v-model:value="form.target_id" placeholder="그룹/조직/엔드포인트 UUID" />
        </n-form-item>
        <n-form-item label="패치 유형">
          <n-checkbox-group v-model:value="form.patch_types">
            <n-space>
              <n-checkbox value="security" label="보안" />
              <n-checkbox value="critical" label="긴급" />
              <n-checkbox value="important" label="중요" />
              <n-checkbox value="optional" label="선택" />
            </n-space>
          </n-checkbox-group>
        </n-form-item>
        <n-form-item label="자동 설치">
          <n-switch v-model:value="form.auto_install" />
        </n-form-item>
        <n-form-item label="동시 설치 수">
          <n-input-number v-model:value="form.max_concurrent" :min="1" :max="100" style="width:100%" />
        </n-form-item>
        <n-form-item label="대역폭 제한(kbps)">
          <n-input-number v-model:value="form.bandwidth_limit_kbps" :min="0" placeholder="제한 없음" style="width:100%" />
        </n-form-item>
        <n-form-item label="설치 윈도우(시작)">
          <n-input v-model:value="form.window_start" placeholder="02:00" />
        </n-form-item>
        <n-form-item label="설치 윈도우(종료)">
          <n-input v-model:value="form.window_end" placeholder="04:00" />
        </n-form-item>
        <n-form-item label="실패 시 롤백">
          <n-switch v-model:value="form.rollback_on_failure" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreate = false">취소</n-button>
          <n-button type="primary" :loading="saving" @click="handleCreate">저장</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, h, onMounted } from 'vue'
import { NTag, NButton, NSpace, useMessage } from 'naive-ui'
import { policyApi, type Policy } from '@/api/deployments'

const message = useMessage()
const policies = ref<Policy[]>([])
const loading = ref(false)
const showCreate = ref(false)
const saving = ref(false)

const form = reactive({
  name: '',
  priority: 100,
  target_type: 'all',
  target_id: '00000000-0000-0000-0000-000000000000',
  patch_types: ['security', 'critical'] as string[],
  auto_install: false,
  max_concurrent: 10,
  bandwidth_limit_kbps: null as number | null,
  rollback_on_failure: true,
  window_start: '',
  window_end: '',
})

const targetTypeOptions = [
  { label: '전체', value: 'all' },
  { label: '그룹', value: 'group' },
  { label: '조직', value: 'organization' },
  { label: '엔드포인트', value: 'endpoint' },
]

const columns = [
  { title: '이름', key: 'name' },
  { title: '우선순위', key: 'priority', width: 90 },
  { title: '대상', key: 'target_type', width: 100 },
  {
    title: '패치 유형',
    key: 'patch_types',
    render: (row: Policy) =>
      h(NSpace, {}, () => row.patch_types.map(t => h(NTag, { size: 'small' }, () => t))),
  },
  {
    title: '자동 설치',
    key: 'auto_install',
    width: 90,
    render: (row: Policy) =>
      h(NTag, { type: row.auto_install ? 'success' : 'default', size: 'small' }, () =>
        row.auto_install ? 'ON' : 'OFF'),
  },
  { title: '동시 설치', key: 'max_concurrent', width: 90 },
  {
    title: '상태',
    key: 'is_active',
    width: 80,
    render: (row: Policy) =>
      h(NTag, { type: row.is_active ? 'success' : 'error', size: 'small' }, () =>
        row.is_active ? '활성' : '비활성'),
  },
  {
    title: '동작',
    key: 'actions',
    width: 100,
    render: (row: Policy) =>
      h(NButton, { size: 'small', type: 'error', onClick: () => handleDelete(row.id) }, () => '삭제'),
  },
]

async function loadPolicies() {
  loading.value = true
  try {
    const resp = await policyApi.list()
    policies.value = resp.data
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  saving.value = true
  try {
    const payload: any = { ...form }
    if (form.window_start && form.window_end) {
      payload.install_window = {
        days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
        start: form.window_start,
        end: form.window_end,
        tz: 'Asia/Seoul',
      }
    }
    delete payload.window_start
    delete payload.window_end
    await policyApi.create(payload)
    message.success('정책이 생성되었습니다')
    showCreate.value = false
    loadPolicies()
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '생성 실패')
  } finally {
    saving.value = false
  }
}

async function handleDelete(id: string) {
  try {
    await policyApi.delete(id)
    message.success('정책이 비활성화되었습니다')
    loadPolicies()
  } catch {
    message.error('삭제 실패')
  }
}

onMounted(loadPolicies)
</script>

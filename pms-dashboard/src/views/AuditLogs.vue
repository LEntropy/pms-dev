<template>
  <div>
    <n-card title="감사 로그">
      <template #header-extra>
        <n-space>
          <n-input
            v-model:value="filterAction"
            placeholder="액션 검색 (예: auth.login)"
            clearable
            style="width: 220px"
            @keydown.enter="loadLogs(1)"
          />
          <n-select
            v-model:value="filterResource"
            :options="resourceOptions"
            placeholder="리소스"
            clearable
            style="width: 130px"
            @update:value="loadLogs(1)"
          />
          <n-button @click="loadLogs(1)">조회</n-button>
        </n-space>
      </template>

      <n-data-table
        :columns="columns"
        :data="logs"
        :loading="loading"
        size="small"
        :max-height="560"
        striped
      />
      <div style="display: flex; justify-content: flex-end; margin-top: 12px">
        <n-pagination
          v-model:page="page"
          :page-count="Math.max(1, Math.ceil(hasMore ? (page + 1) * pageSize : page * pageSize) / pageSize)"
          @update:page="loadLogs"
        />
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NTag, NTime } from 'naive-ui'
import api from '@/api/client'

interface AuditLog {
  id: number
  actor_type: string
  actor_id: string | null
  action: string
  resource: string | null
  resource_id: string | null
  detail: Record<string, any> | null
  ip_address: string | null
  occurred_at: string
}

const logs = ref<AuditLog[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 50
const hasMore = ref(false)
const filterAction = ref('')
const filterResource = ref<string | null>(null)

const resourceOptions = [
  { label: '엔드포인트', value: 'endpoint' },
  { label: '태스크', value: 'task' },
  { label: '배포', value: 'deployment' },
]

const actorTypeColor: Record<string, 'info' | 'success' | 'default'> = {
  user: 'info',
  agent: 'success',
  system: 'default',
}

const columns = [
  {
    title: '발생 시각',
    key: 'occurred_at',
    width: 160,
    render: (row: AuditLog) => new Date(row.occurred_at).toLocaleString('ko-KR'),
  },
  {
    title: '주체',
    key: 'actor_type',
    width: 80,
    render: (row: AuditLog) =>
      h(NTag, { type: actorTypeColor[row.actor_type] ?? 'default', size: 'small' }, () => row.actor_type),
  },
  {
    title: '주체 ID',
    key: 'actor_id',
    width: 120,
    render: (row: AuditLog) => row.actor_id ? row.actor_id.slice(0, 8) + '…' : '-',
  },
  { title: '액션', key: 'action', ellipsis: { tooltip: true } },
  { title: '리소스', key: 'resource', width: 110 },
  {
    title: 'IP',
    key: 'ip_address',
    width: 120,
    render: (row: AuditLog) => row.ip_address ?? '-',
  },
  {
    title: '상세',
    key: 'detail',
    ellipsis: { tooltip: true },
    render: (row: AuditLog) =>
      row.detail ? JSON.stringify(row.detail).slice(0, 80) : '-',
  },
]

async function loadLogs(p?: number) {
  if (p) page.value = p
  loading.value = true
  try {
    const params: Record<string, any> = { page: page.value, page_size: pageSize }
    if (filterAction.value) params.action = filterAction.value
    if (filterResource.value) params.resource = filterResource.value
    const resp = await api.get<AuditLog[]>('/audit', { params })
    logs.value = resp.data
    hasMore.value = resp.data.length === pageSize
  } finally {
    loading.value = false
  }
}

onMounted(() => loadLogs())
</script>

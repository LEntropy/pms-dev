<template>
  <div class="dashboard">
    <n-grid :cols="5" :x-gap="16" :y-gap="16" style="margin-bottom: 24px">
      <n-gi>
        <n-statistic label="전체 엔드포인트" :value="stats?.total ?? 0" />
      </n-gi>
      <n-gi>
        <n-statistic label="온라인" :value="onlineCount">
          <template #prefix>
            <n-badge type="success" dot />
          </template>
        </n-statistic>
      </n-gi>
      <n-gi>
        <n-statistic label="Windows" :value="stats?.by_platform?.windows ?? 0" />
      </n-gi>
      <n-gi>
        <n-statistic label="Linux" :value="stats?.by_platform?.linux ?? 0" />
      </n-gi>
      <n-gi>
        <n-statistic
          label="평균 컴플라이언스"
          :value="compliance?.avg_compliance_pct ?? 100"
          suffix="%"
          :precision="1"
        />
      </n-gi>
    </n-grid>

    <n-card title="엔드포인트 현황">
      <n-data-table
        :columns="columns"
        :data="endpoints"
        :loading="loading"
        :pagination="{ pageSize: 20 }"
        :row-key="(row: any) => row.id"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, h } from 'vue'
import { NTag, NBadge } from 'naive-ui'
import { endpointApi, type Endpoint, type EndpointStats } from '@/api/endpoints'
import { patchApi, type ComplianceSummary } from '@/api/patches'

const endpoints = ref<Endpoint[]>([])
const stats = ref<EndpointStats | null>(null)
const compliance = ref<ComplianceSummary | null>(null)
const loading = ref(false)
let ws: WebSocket | null = null

const onlineCount = computed(() => endpoints.value.filter(e => e.is_online).length)

const columns = [
  {
    title: '상태',
    key: 'is_online',
    width: 80,
    render(row: Endpoint) {
      return h(NBadge, {
        type: row.is_online ? 'success' : 'default',
        dot: true,
      })
    },
  },
  { title: '호스트명', key: 'hostname' },
  { title: 'IP 주소', key: 'ip_address' },
  { title: '플랫폼', key: 'platform', width: 100 },
  { title: 'OS', key: 'os_name' },
  { title: '에이전트', key: 'agent_version', width: 100 },
  {
    title: '마지막 연결',
    key: 'last_seen_at',
    render(row: Endpoint) {
      if (!row.last_seen_at) return '-'
      return new Date(row.last_seen_at).toLocaleString('ko-KR')
    },
  },
  {
    title: '상태',
    key: 'status',
    render(row: Endpoint) {
      const typeMap: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
        active: 'success',
        quarantined: 'warning',
        decommissioned: 'error',
        inactive: 'default',
      }
      return h(NTag, { type: typeMap[row.status] ?? 'default', size: 'small' }, () => row.status)
    },
  },
]

async function loadData() {
  loading.value = true
  try {
    const [epResp, statsResp, compResp] = await Promise.all([
      endpointApi.list({ page_size: 200 }),
      endpointApi.stats(),
      patchApi.complianceSummary().catch(() => null),
    ])
    endpoints.value = epResp.data.items
    stats.value = statsResp.data
    if (compResp) compliance.value = compResp.data
  } finally {
    loading.value = false
  }
}

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/endpoints/status`)

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'endpoint_status_change') {
      const ep = endpoints.value.find(e => e.id === data.endpoint_id)
      if (ep) ep.is_online = data.is_online
    }
  }

  ws.onclose = () => {
    setTimeout(connectWs, 5000)
  }
}

onMounted(() => {
  loadData()
  connectWs()
})

onUnmounted(() => {
  ws?.close()
})
</script>

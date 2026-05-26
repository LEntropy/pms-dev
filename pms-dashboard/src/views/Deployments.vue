<template>
  <div>
    <!-- 요약 카드 -->
    <n-grid :cols="4" :x-gap="12" style="margin-bottom: 20px">
      <n-gi v-for="(count, status) in stats" :key="status">
        <n-card size="small">
          <n-statistic :label="statusLabel(status)" :value="count" />
        </n-card>
      </n-gi>
    </n-grid>

    <!-- 배포 목록 + 생성 -->
    <n-card title="배포 목록">
      <template #header-extra>
        <n-button type="primary" size="small" @click="showCreate = true">새 배포</n-button>
      </template>
      <n-data-table :columns="columns" :data="deployments" :loading="loading" @row-click="openDetail" />
    </n-card>

    <!-- 배포 생성 모달 -->
    <n-modal v-model:show="showCreate" title="배포 생성" preset="card" style="width: 520px">
      <n-form :model="createForm" label-placement="left" label-width="110">
        <n-form-item label="패치 ID">
          <n-input v-model:value="createForm.patch_id" placeholder="Patch UUID" />
        </n-form-item>
        <n-form-item label="정책 ID (선택)">
          <n-input v-model:value="createForm.policy_id" placeholder="Policy UUID" />
        </n-form-item>
        <n-form-item label="대상 유형">
          <n-select v-model:value="createForm.target_type" :options="targetTypeOptions" />
        </n-form-item>
        <n-form-item v-if="createForm.target_type !== 'all'" label="대상 ID">
          <n-input v-model:value="createForm.target_id" placeholder="Group/Endpoint UUID" />
        </n-form-item>
        <n-form-item label="예약 시간 (선택)">
          <n-date-picker v-model:value="createForm.scheduled_at" type="datetime" clearable />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreate = false">취소</n-button>
          <n-button type="primary" :loading="creating" @click="handleCreate">배포 시작</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 배포 상세 / 실시간 진행 드로어 -->
    <n-drawer v-model:show="showDetail" :width="640" placement="right">
      <n-drawer-content :title="`배포 상세 — ${selectedDeployment?.id?.slice(0, 8)}...`" closable>
        <div v-if="selectedDeployment" style="margin-bottom: 12px">
          <n-descriptions :column="2" bordered size="small">
            <n-descriptions-item label="상태">
              <n-tag :type="statusType(selectedDeployment.status)" size="small">
                {{ selectedDeployment.status }}
              </n-tag>
            </n-descriptions-item>
            <n-descriptions-item label="전체 대상">{{ selectedDeployment.total_targets ?? '-' }}</n-descriptions-item>
            <n-descriptions-item label="성공">{{ selectedDeployment.success_count }}</n-descriptions-item>
            <n-descriptions-item label="실패">{{ selectedDeployment.failure_count }}</n-descriptions-item>
          </n-descriptions>
        </div>

        <!-- 실시간 진행 상황 (WebSocket) -->
        <n-card title="엔드포인트별 진행" size="small" style="margin-bottom: 12px">
          <n-data-table
            :columns="resultColumns"
            :data="results"
            size="small"
            :max-height="360"
          />
        </n-card>

        <n-space>
          <n-button
            v-if="selectedDeployment?.status === 'in_progress'"
            type="warning"
            @click="handleCancel"
          >배포 취소</n-button>
          <n-button
            v-if="selectedDeployment?.status === 'failed'"
            type="error"
            @click="handleRollback"
          >롤백</n-button>
        </n-space>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h, onMounted, onUnmounted, watch } from 'vue'
import { NTag, NProgress } from 'naive-ui'
import { deploymentApi, type Deployment, type DeploymentResult } from '@/api/deployments'
import { useMessage } from 'naive-ui'

const message = useMessage()
const deployments = ref<Deployment[]>([])
const results = ref<DeploymentResult[]>([])
const stats = ref<Record<string, number>>({})
const loading = ref(false)
const creating = ref(false)
const showCreate = ref(false)
const showDetail = ref(false)
const selectedDeployment = ref<Deployment | null>(null)
let ws: WebSocket | null = null

const createForm = reactive({
  patch_id: '',
  policy_id: '',
  target_type: 'all',
  target_id: '',
  scheduled_at: null as number | null,
})

const targetTypeOptions = [
  { label: '전체', value: 'all' },
  { label: '그룹', value: 'group' },
  { label: '엔드포인트', value: 'endpoint' },
]

const statusColor: Record<string, 'success' | 'warning' | 'error' | 'default' | 'info'> = {
  completed: 'success',
  in_progress: 'info',
  failed: 'error',
  cancelled: 'warning',
  pending: 'default',
  rolled_back: 'warning',
}

function statusType(s: string): 'success' | 'warning' | 'error' | 'default' | 'info' {
  return statusColor[s] ?? 'default'
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    completed: '완료', in_progress: '진행 중', failed: '실패',
    cancelled: '취소됨', pending: '대기 중', rolled_back: '롤백됨',
  }
  return map[s] ?? s
}

const columns = [
  {
    title: '상태',
    key: 'status',
    width: 100,
    render: (row: Deployment) =>
      h(NTag, { type: statusType(row.status), size: 'small' }, () => row.status),
  },
  { title: '패치 ID', key: 'patch_id', ellipsis: { tooltip: true } },
  { title: '대상', key: 'target_type', width: 90 },
  {
    title: '진행',
    key: 'progress',
    width: 140,
    render: (row: Deployment) => {
      if (!row.total_targets) return '-'
      const done = row.success_count + row.failure_count
      const pct = Math.round((done / row.total_targets) * 100)
      return h(NProgress, { percentage: pct, type: 'line', showIndicator: true, status: row.failure_count > 0 ? 'error' : 'default' })
    },
  },
  {
    title: '생성일',
    key: 'created_at',
    render: (row: Deployment) => new Date(row.created_at).toLocaleString('ko-KR'),
  },
]

const resultColumns = [
  {
    title: '상태',
    key: 'status',
    width: 100,
    render: (row: DeploymentResult) =>
      h(NTag, { type: statusType(row.status), size: 'small' }, () => row.status),
  },
  { title: '엔드포인트', key: 'endpoint_id', ellipsis: { tooltip: true } },
  { title: '종료코드', key: 'exit_code', width: 90 },
  { title: '오류', key: 'error_message', ellipsis: { tooltip: true } },
]

async function loadDeployments() {
  loading.value = true
  try {
    const [depResp, statsResp] = await Promise.all([
      deploymentApi.list(),
      deploymentApi.stats(),
    ])
    deployments.value = depResp.data
    stats.value = statsResp.data.by_status
  } finally {
    loading.value = false
  }
}

async function openDetail(row: Deployment) {
  selectedDeployment.value = row
  showDetail.value = true
  const resp = await deploymentApi.results(row.id)
  results.value = resp.data
}

// WebSocket: 실시간 배포 진행 수신
function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/endpoints/status`)
  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data)
    if (data.type === 'deployment_progress') {
      // 현재 상세 드로어에 표시 중인 배포면 결과 행 갱신
      if (selectedDeployment.value?.id === data.deployment_id) {
        const idx = results.value.findIndex(r => r.endpoint_id === data.endpoint_id)
        if (idx !== -1) {
          results.value[idx] = { ...results.value[idx], status: data.status, error_message: data.error_message }
        }
      }
      // 목록의 해당 배포 카운터도 갱신
      const dep = deployments.value.find(d => d.id === data.deployment_id)
      if (dep && ['success', 'failed', 'rolled_back'].includes(data.status)) {
        if (data.status === 'success') dep.success_count++
        else dep.failure_count++
      }
    }
  }
  ws.onclose = () => setTimeout(connectWs, 5000)
}

async function handleCreate() {
  creating.value = true
  try {
    const payload: any = {
      patch_id: createForm.patch_id,
      target_type: createForm.target_type,
      policy_id: createForm.policy_id || undefined,
      target_id: createForm.target_type !== 'all' ? createForm.target_id : undefined,
      scheduled_at: createForm.scheduled_at
        ? new Date(createForm.scheduled_at).toISOString() : undefined,
    }
    await deploymentApi.create(payload)
    message.success('배포가 생성되었습니다')
    showCreate.value = false
    loadDeployments()
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '배포 생성 실패')
  } finally {
    creating.value = false
  }
}

async function handleCancel() {
  if (!selectedDeployment.value) return
  await deploymentApi.cancel(selectedDeployment.value.id)
  message.success('배포가 취소되었습니다')
  showDetail.value = false
  loadDeployments()
}

async function handleRollback() {
  if (!selectedDeployment.value) return
  const resp = await deploymentApi.rollback(selectedDeployment.value.id)
  message.success(`롤백 큐 삽입: ${resp.data.rollback_queued}대`)
  loadDeployments()
}

onMounted(() => { loadDeployments(); connectWs() })
onUnmounted(() => ws?.close())
</script>

<template>
  <div>
    <n-tabs v-model:value="activeTab" type="line" animated>
      <!-- 컴플라이언스 현황 탭 -->
      <n-tab-pane name="compliance" tab="컴플라이언스 현황">
        <n-grid :cols="3" :x-gap="12" style="margin-bottom: 20px">
          <n-gi>
            <n-card size="small">
              <n-statistic label="전체 엔드포인트" :value="summary.total_endpoints ?? 0" />
            </n-card>
          </n-gi>
          <n-gi>
            <n-card size="small">
              <n-statistic label="평균 준수율">
                <template #default>
                  <span :style="{ color: complianceColor(summary.avg_compliance_pct) }">
                    {{ summary.avg_compliance_pct?.toFixed(1) ?? '-' }}%
                  </span>
                </template>
              </n-statistic>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card size="small">
              <n-statistic label="미준수 엔드포인트" :value="summary.non_compliant_count ?? 0" />
            </n-card>
          </n-gi>
        </n-grid>

        <n-card title="상태별 분포" :loading="summaryLoading" style="margin-bottom: 16px">
          <div v-if="summary.compliance_distribution" style="display: flex; gap: 24px; flex-wrap: wrap">
            <div v-for="(count, band) in summary.compliance_distribution" :key="band" style="text-align: center">
              <n-progress
                type="circle"
                :percentage="Number(band.split('-')[0])"
                :status="circleStatus(band)"
                style="width: 80px"
              />
              <div style="margin-top: 4px; font-size: 12px; color: #888">{{ band }}%</div>
              <div style="font-size: 14px; font-weight: 600">{{ count }}대</div>
            </div>
          </div>
        </n-card>

        <n-card title="CVE 노출 엔드포인트" :loading="cveLoading">
          <template #header-extra>
            <n-input
              v-model:value="patchIdFilter"
              placeholder="패치 UUID 입력 후 Enter"
              style="width: 300px"
              @keydown.enter="loadCveExposure"
            />
          </template>
          <n-data-table
            :columns="cveColumns"
            :data="cveExposure"
            size="small"
            :max-height="320"
          />
        </n-card>
      </n-tab-pane>

      <!-- 배포 트렌드 탭 -->
      <n-tab-pane name="deployments" tab="배포 트렌드">
        <n-card title="배포 현황 요약" :loading="deployStatsLoading" style="margin-bottom: 16px">
          <n-grid :cols="6" :x-gap="12">
            <n-gi v-for="(count, status) in deployStats" :key="status">
              <n-card size="small" embedded>
                <n-statistic :label="deployLabel(status)" :value="count" />
              </n-card>
            </n-gi>
          </n-grid>
        </n-card>

        <n-card title="최근 배포 목록">
          <n-data-table
            :columns="deployColumns"
            :data="recentDeploys"
            :loading="deploysLoading"
            size="small"
            :max-height="400"
          />
        </n-card>
      </n-tab-pane>

      <!-- 누락 패치 탭 -->
      <n-tab-pane name="missing" tab="누락 패치 현황">
        <n-card title="패치별 미적용 엔드포인트 수">
          <template #header-extra>
            <n-input
              v-model:value="missingPatchFilter"
              placeholder="패치 ID 검색"
              clearable
              style="width: 240px"
            />
          </template>
          <n-data-table
            :columns="missingColumns"
            :data="filteredMissingPatches"
            size="small"
            :max-height="460"
          />
        </n-card>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, watch } from 'vue'
import { NTag, NProgress } from 'naive-ui'
import { deploymentApi } from '@/api/deployments'
import type { Deployment } from '@/api/deployments'
import { endpointApi } from '@/api/endpoints'
import { patchApi } from '@/api/patches'

const activeTab = ref('compliance')
const summaryLoading = ref(false)
const cveLoading = ref(false)
const deployStatsLoading = ref(false)
const deploysLoading = ref(false)

const summary = ref<any>({})
const patchIdFilter = ref('')
const cveExposure = ref<any[]>([])
const deployStats = ref<Record<string, number>>({})
const recentDeploys = ref<Deployment[]>([])
const missingPatches = ref<any[]>([])
const missingPatchFilter = ref('')

async function loadSummary() {
  summaryLoading.value = true
  try {
    const resp = await endpointApi.complianceSummary()
    summary.value = resp.data
  } finally {
    summaryLoading.value = false
  }
}

async function loadCveExposure() {
  if (!patchIdFilter.value.trim()) return
  cveLoading.value = true
  try {
    const resp = await patchApi.affectedEndpoints(patchIdFilter.value.trim())
    cveExposure.value = (resp.data as any).affected_endpoints ?? []
  } finally {
    cveLoading.value = false
  }
}

async function loadDeployStats() {
  deployStatsLoading.value = true
  try {
    const resp = await deploymentApi.stats()
    deployStats.value = resp.data.by_status
  } finally {
    deployStatsLoading.value = false
  }
}

async function loadRecentDeploys() {
  deploysLoading.value = true
  try {
    const resp = await deploymentApi.list({ page: 1 })
    recentDeploys.value = resp.data
  } finally {
    deploysLoading.value = false
  }
}

function complianceColor(pct: number): string {
  if (pct >= 80) return '#18a058'
  if (pct >= 50) return '#f0a020'
  return '#d03050'
}

function circleStatus(band: string): 'success' | 'warning' | 'error' | 'default' {
  const start = parseInt(band.split('-')[0])
  if (start >= 80) return 'success'
  if (start >= 50) return 'warning'
  return 'error'
}

const deployLabelMap: Record<string, string> = {
  pending: '대기', in_progress: '진행 중', completed: '완료',
  failed: '실패', cancelled: '취소', rolled_back: '롤백',
}
function deployLabel(s: string) {
  return deployLabelMap[s] ?? s
}

const deployStatusColor: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  completed: 'success', in_progress: 'info', failed: 'error', cancelled: 'warning', pending: 'default', rolled_back: 'warning',
}

const cveColumns = [
  { title: '엔드포인트 ID', key: 'endpoint_id', ellipsis: { tooltip: true } },
  { title: '호스트명', key: 'hostname' },
  { title: '현재 버전', key: 'installed_version', width: 130 },
]

const deployColumns = [
  {
    title: '상태',
    key: 'status',
    width: 100,
    render: (row: Deployment) =>
      h(NTag, { type: deployStatusColor[row.status] ?? 'default', size: 'small' }, () => row.status),
  },
  { title: '패치 ID', key: 'patch_id', ellipsis: { tooltip: true } },
  { title: '대상', key: 'target_type', width: 90 },
  {
    title: '진행',
    key: 'progress',
    width: 80,
    render: (row: Deployment) => {
      if (!row.total_targets) return '-'
      const done = row.success_count + row.failure_count
      return `${done}/${row.total_targets}`
    },
  },
  {
    title: '생성일',
    key: 'created_at',
    render: (row: Deployment) => new Date(row.created_at).toLocaleString('ko-KR'),
  },
]

const missingColumns = [
  { title: '패치명', key: 'patch_name', ellipsis: { tooltip: true } },
  { title: '패치 ID', key: 'patch_id', ellipsis: { tooltip: true } },
  {
    title: '심각도',
    key: 'severity',
    width: 90,
    render: (row: any) =>
      h(NTag, { size: 'small', type: row.severity === 'critical' ? 'error' : row.severity === 'security' ? 'warning' : 'default' }, () => row.severity),
  },
  { title: '미적용 엔드포인트 수', key: 'affected_count', width: 160 },
]

const filteredMissingPatches = computed(() => {
  const q = missingPatchFilter.value.toLowerCase()
  if (!q) return missingPatches.value
  return missingPatches.value.filter(p =>
    p.patch_name?.toLowerCase().includes(q) || p.patch_id?.toLowerCase().includes(q)
  )
})

watch(activeTab, (tab) => {
  if (tab === 'deployments' && recentDeploys.value.length === 0) {
    loadDeployStats()
    loadRecentDeploys()
  }
})

onMounted(() => {
  loadSummary()
  loadDeployStats()
  loadRecentDeploys()
})
</script>

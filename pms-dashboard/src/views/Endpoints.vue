<template>
  <div>
    <!-- 요약 카드 -->
    <n-grid :cols="4" :x-gap="12" style="margin-bottom: 20px">
      <n-gi>
        <n-card size="small">
          <n-statistic label="전체" :value="stats.total ?? 0" />
        </n-card>
      </n-gi>
      <n-gi v-for="(count, platform) in stats.by_platform" :key="platform">
        <n-card size="small">
          <n-statistic :label="platform" :value="count" />
        </n-card>
      </n-gi>
    </n-grid>

    <!-- 필터 + 목록 -->
    <n-card title="엔드포인트 목록">
      <template #header-extra>
        <n-space>
          <n-select
            v-model:value="filterStatus"
            :options="statusOptions"
            placeholder="상태 필터"
            clearable
            style="width: 130px"
            @update:value="loadEndpoints(1)"
          />
          <n-select
            v-model:value="filterPlatform"
            :options="platformOptions"
            placeholder="플랫폼"
            clearable
            style="width: 120px"
            @update:value="loadEndpoints(1)"
          />
          <n-button size="small" @click="showUpgradeModal = true">업그레이드 푸시</n-button>
          <n-button type="primary" size="small" @click="showTokenModal = true">등록 토큰 발급</n-button>
        </n-space>
      </template>

      <n-data-table
        :columns="columns"
        :data="endpoints"
        :loading="loading"
        :row-props="rowProps"
        style="cursor: pointer"
      />
      <div style="display: flex; justify-content: flex-end; margin-top: 12px">
        <n-pagination
          v-model:page="page"
          :page-count="Math.ceil(total / pageSize)"
          @update:page="loadEndpoints"
        />
      </div>
    </n-card>

    <!-- 에이전트 업그레이드 모달 -->
    <n-modal v-model:show="showUpgradeModal" title="에이전트 업그레이드 푸시" preset="card" style="width: 500px">
      <n-form label-placement="left" label-width="120">
        <n-form-item label="대상">
          <n-select v-model:value="upgradeForm.target" :options="upgradeTargetOptions" style="width: 100%" />
        </n-form-item>
        <n-form-item label="버전">
          <n-input v-model:value="upgradeForm.version" placeholder="예: 0.2.0" />
        </n-form-item>
        <n-form-item label="다운로드 URL">
          <n-input v-model:value="upgradeForm.download_url" placeholder="https://…/pms-agent.exe" />
        </n-form-item>
        <n-form-item label="SHA-256">
          <n-input v-model:value="upgradeForm.file_hash_sha256" placeholder="64자 hex" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showUpgradeModal = false">취소</n-button>
          <n-button type="primary" :loading="upgradeLoading" @click="handleUpgrade">푸시</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 등록 토큰 발급 모달 -->
    <n-modal v-model:show="showTokenModal" title="등록 토큰 발급" preset="card" style="width: 440px">
      <n-form label-placement="left" label-width="120">
        <n-form-item label="레이블">
          <n-input v-model:value="tokenForm.label" placeholder="예: 서버실-A" />
        </n-form-item>
        <n-form-item label="유효 시간(h)">
          <n-input-number v-model:value="tokenForm.expires_hours" :min="1" :max="720" style="width:100%" />
        </n-form-item>
      </n-form>
      <div v-if="generatedToken" style="margin-top: 12px">
        <n-alert type="success" title="토큰 발급 완료">
          <n-code>{{ generatedToken }}</n-code>
        </n-alert>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showTokenModal = false; generatedToken = ''">닫기</n-button>
          <n-button type="primary" :loading="tokenLoading" @click="handleIssueToken">발급</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 엔드포인트 상세 드로어 -->
    <n-drawer v-model:show="showDetail" :width="680" placement="right">
      <n-drawer-content :title="selectedEndpoint?.hostname ?? '상세'" closable>
        <div v-if="selectedEndpoint">
          <n-descriptions :column="2" bordered size="small" style="margin-bottom: 16px">
            <n-descriptions-item label="상태">
              <n-tag :type="statusType(selectedEndpoint.status)" size="small">
                {{ selectedEndpoint.status }}
              </n-tag>
              &nbsp;
              <n-badge v-if="selectedEndpoint.is_online" dot type="success" />
              <n-badge v-else dot type="error" />
            </n-descriptions-item>
            <n-descriptions-item label="플랫폼">{{ selectedEndpoint.platform }}</n-descriptions-item>
            <n-descriptions-item label="OS">{{ selectedEndpoint.os_name }} {{ selectedEndpoint.os_version }}</n-descriptions-item>
            <n-descriptions-item label="IP">{{ selectedEndpoint.ip_address ?? '-' }}</n-descriptions-item>
            <n-descriptions-item label="에이전트 버전">{{ selectedEndpoint.agent_version ?? '-' }}</n-descriptions-item>
            <n-descriptions-item label="마지막 접속">
              {{ selectedEndpoint.last_seen_at ? new Date(selectedEndpoint.last_seen_at).toLocaleString('ko-KR') : '-' }}
            </n-descriptions-item>
          </n-descriptions>

          <n-tabs default-value="software">
            <n-tab-pane name="software" tab="설치 소프트웨어">
              <n-data-table
                :columns="softwareColumns"
                :data="software"
                :loading="softwareLoading"
                size="small"
                :max-height="380"
              />
            </n-tab-pane>
            <n-tab-pane name="compliance" tab="컴플라이언스">
              <div v-if="compliance">
                <n-statistic label="준수율" style="margin-bottom: 12px">
                  <template #default>
                    <n-progress
                      type="line"
                      :percentage="compliance.compliance_pct"
                      :status="compliance.compliance_pct >= 80 ? 'success' : compliance.compliance_pct >= 50 ? 'warning' : 'error'"
                      :show-indicator="true"
                    />
                  </template>
                </n-statistic>
                <n-data-table
                  :columns="complianceColumns"
                  :data="compliance.missing_patches"
                  size="small"
                  :max-height="300"
                />
              </div>
              <n-spin v-else-if="complianceLoading" />
            </n-tab-pane>
          </n-tabs>

          <n-divider />
          <n-space>
            <n-popconfirm @positive-click="handleQuarantine">
              <template #trigger>
                <n-button type="warning" size="small" :disabled="selectedEndpoint.status === 'quarantined'">격리</n-button>
              </template>
              격리하시겠습니까?
            </n-popconfirm>
            <n-popconfirm @positive-click="handleDecommission">
              <template #trigger>
                <n-button type="error" size="small">폐기</n-button>
              </template>
              폐기 처리하시겠습니까?
            </n-popconfirm>
          </n-space>
        </div>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted } from 'vue'
import { NTag, NBadge, NProgress, useMessage } from 'naive-ui'
import { endpointApi, type Endpoint, type EndpointStats, type SoftwareEntry, type ComplianceResult } from '@/api/endpoints'
import api from '@/api/client'

const message = useMessage()
const endpoints = ref<Endpoint[]>([])
const stats = ref<EndpointStats>({ by_status: {}, by_platform: {}, total: 0 })
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 50
const filterStatus = ref<string | null>(null)
const filterPlatform = ref<string | null>(null)
const showTokenModal = ref(false)
const tokenLoading = ref(false)
const generatedToken = ref('')
const tokenForm = ref({ label: '', expires_hours: 24 })
const showUpgradeModal = ref(false)
const upgradeLoading = ref(false)
const upgradeForm = ref({ target: 'all', version: '', download_url: '', file_hash_sha256: '' })
const showDetail = ref(false)
const selectedEndpoint = ref<Endpoint | null>(null)
const software = ref<SoftwareEntry[]>([])
const softwareLoading = ref(false)
const compliance = ref<ComplianceResult | null>(null)
const complianceLoading = ref(false)

const statusOptions = [
  { label: '활성', value: 'active' },
  { label: '격리', value: 'quarantined' },
  { label: '폐기', value: 'decommissioned' },
]

const platformOptions = [
  { label: 'Windows', value: 'windows' },
  { label: 'Linux', value: 'linux' },
]

const upgradeTargetOptions = computed(() => [
  { label: '전체 활성 엔드포인트', value: 'all' },
  ...endpoints.value.map(ep => ({ label: `${ep.hostname} (${ep.id.slice(0, 8)})`, value: ep.id })),
])

const statusColor: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  active: 'success',
  quarantined: 'warning',
  decommissioned: 'error',
}

function statusType(s: string): 'success' | 'warning' | 'error' | 'default' {
  return statusColor[s] ?? 'default'
}

const columns = [
  {
    title: '온라인',
    key: 'is_online',
    width: 70,
    render: (row: Endpoint) =>
      h(NBadge, { dot: true, type: row.is_online ? 'success' : 'error' }),
  },
  { title: '호스트명', key: 'hostname' },
  { title: 'IP', key: 'ip_address', width: 130 },
  { title: '플랫폼', key: 'platform', width: 100 },
  { title: 'OS', key: 'os_name', ellipsis: { tooltip: true } },
  {
    title: '상태',
    key: 'status',
    width: 100,
    render: (row: Endpoint) =>
      h(NTag, { type: statusType(row.status), size: 'small' }, () => row.status),
  },
  {
    title: '마지막 접속',
    key: 'last_seen_at',
    render: (row: Endpoint) =>
      row.last_seen_at ? new Date(row.last_seen_at).toLocaleString('ko-KR') : '-',
  },
]

const softwareColumns = [
  { title: '이름', key: 'raw_name', ellipsis: { tooltip: true } },
  { title: '버전', key: 'version', width: 120 },
  { title: '벤더', key: 'vendor', width: 150, ellipsis: { tooltip: true } },
]

const complianceColumns = [
  { title: '패치명', key: 'patch_name', ellipsis: { tooltip: true } },
  { title: '버전', key: 'required_version', width: 120 },
  {
    title: '심각도',
    key: 'severity',
    width: 90,
    render: (row: any) => h(NTag, { size: 'small', type: row.severity === 'critical' ? 'error' : 'warning' }, () => row.severity),
  },
]

function rowProps(row: Endpoint) {
  return {
    onClick: () => openDetail(row),
  }
}

async function loadEndpoints(p?: number) {
  if (p) page.value = p
  loading.value = true
  try {
    const resp = await endpointApi.list({
      page: page.value,
      page_size: pageSize,
      status: filterStatus.value ?? undefined,
      platform: filterPlatform.value ?? undefined,
    })
    endpoints.value = resp.data.items
    total.value = resp.data.total
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const resp = await endpointApi.stats()
  stats.value = resp.data
}

async function openDetail(row: Endpoint) {
  selectedEndpoint.value = row
  showDetail.value = true
  compliance.value = null
  software.value = []

  softwareLoading.value = true
  complianceLoading.value = true
  try {
    const [swResp, compResp] = await Promise.all([
      endpointApi.software(row.id),
      endpointApi.compliance(row.id),
    ])
    software.value = swResp.data.software
    compliance.value = compResp.data
  } finally {
    softwareLoading.value = false
    complianceLoading.value = false
  }
}

async function handleIssueToken() {
  tokenLoading.value = true
  try {
    const resp = await endpointApi.createEnrollmentToken({
      label: tokenForm.value.label || undefined,
      expires_hours: tokenForm.value.expires_hours,
    })
    generatedToken.value = (resp.data as any).token
  } catch {
    message.error('토큰 발급 실패')
  } finally {
    tokenLoading.value = false
  }
}

async function handleQuarantine() {
  if (!selectedEndpoint.value) return
  await endpointApi.quarantine(selectedEndpoint.value.id)
  message.success('격리 처리되었습니다')
  showDetail.value = false
  loadEndpoints()
}

async function handleDecommission() {
  if (!selectedEndpoint.value) return
  await endpointApi.decommission(selectedEndpoint.value.id)
  message.success('폐기 처리되었습니다')
  showDetail.value = false
  loadEndpoints()
}

async function handleUpgrade() {
  const { version, download_url, file_hash_sha256, target } = upgradeForm.value
  if (!version || !download_url || !file_hash_sha256) {
    message.warning('버전, URL, SHA-256 해시를 모두 입력하세요')
    return
  }
  upgradeLoading.value = true
  try {
    const resp = await api.post('/agent-admin/upgrade', { target, version, download_url, file_hash_sha256 })
    message.success(`업그레이드 태스크 ${(resp.data as any).queued}대에 푸시됨`)
    showUpgradeModal.value = false
    upgradeForm.value = { target: 'all', version: '', download_url: '', file_hash_sha256: '' }
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '업그레이드 푸시 실패')
  } finally {
    upgradeLoading.value = false
  }
}

onMounted(() => {
  loadEndpoints()
  loadStats()
})
</script>

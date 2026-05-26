<template>
  <div>
    <n-tabs v-model:value="activeTab" type="line" animated>

      <!-- LDAP 동기화 탭 -->
      <n-tab-pane name="ldap" tab="LDAP/AD 동기화">
        <n-card title="LDAP / Active Directory 연동" style="margin-bottom: 16px">
          <n-descriptions :column="2" bordered size="small" style="margin-bottom: 16px">
            <n-descriptions-item label="설정 여부">
              <n-tag :type="ldapStatus.configured ? 'success' : 'warning'" size="small">
                {{ ldapStatus.configured ? '설정됨' : '미설정' }}
              </n-tag>
            </n-descriptions-item>
            <n-descriptions-item label="연결 상태">
              <n-tag :type="ldapStatus.connected ? 'success' : 'error'" size="small">
                {{ ldapStatus.connected ? '연결됨' : '연결 안됨' }}
              </n-tag>
            </n-descriptions-item>
          </n-descriptions>
          <n-space>
            <n-button type="primary" :loading="ldapSyncing" @click="handleLdapSync">
              즉시 동기화
            </n-button>
            <n-text depth="3" style="font-size: 12px">매일 02:00 자동 실행</n-text>
          </n-space>
        </n-card>
      </n-tab-pane>

      <!-- 리포트 탭 -->
      <n-tab-pane name="reports" tab="리포트">
        <n-card title="컴플라이언스 PDF 리포트" style="margin-bottom: 16px">
          <n-space style="margin-bottom: 16px">
            <n-button type="primary" :loading="reportGenerating" @click="handleGenerateReport">
              즉시 생성
            </n-button>
            <n-button @click="loadReports">새로고침</n-button>
            <n-text depth="3" style="font-size: 12px">매주 월요일 08:00 자동 생성</n-text>
          </n-space>

          <n-data-table
            :columns="reportColumns"
            :data="reports"
            :loading="reportsLoading"
            size="small"
          />
        </n-card>
      </n-tab-pane>

      <!-- OpenVAS 탭 -->
      <n-tab-pane name="openvas" tab="OpenVAS 스캔">
        <n-card title="취약점 스캐너 (OpenVAS / Greenbone)">
          <n-alert type="info" style="margin-bottom: 16px">
            OpenVAS URL이 설정되어 있어야 스캔이 실행됩니다. (.env: OPENVAS_URL)
          </n-alert>
          <n-space>
            <n-button type="warning" :loading="scanRunning" @click="handleOpenvasScan">
              즉시 스캔 트리거
            </n-button>
            <n-text depth="3" style="font-size: 12px">매주 일요일 03:00 자동 실행</n-text>
          </n-space>
        </n-card>
      </n-tab-pane>

      <!-- 자사 SW 자동 배포 탭 -->
      <n-tab-pane name="watched" tab="자동 배포 감시">
        <n-card title="자사 SW 자동 배포 감시 목록">
          <template #header-extra>
            <n-button type="primary" size="small" @click="showWatchedModal = true">감시 추가</n-button>
          </template>
          <n-data-table
            :columns="watchedColumns"
            :data="watchedProducts"
            :loading="watchedLoading"
            size="small"
          />
        </n-card>

        <!-- 감시 추가 모달 -->
        <n-modal v-model:show="showWatchedModal" title="자동 배포 감시 추가" preset="card" style="width: 500px">
          <n-form label-placement="left" label-width="120">
            <n-form-item label="제품 ID">
              <n-input v-model:value="watchedForm.product_id" placeholder="SoftwareProduct UUID" />
            </n-form-item>
            <n-form-item label="대상 유형">
              <n-select v-model:value="watchedForm.target_type" :options="targetOptions" />
            </n-form-item>
            <n-form-item v-if="watchedForm.target_type !== 'all'" label="대상 ID">
              <n-input v-model:value="watchedForm.target_id" placeholder="Group/Endpoint UUID" />
            </n-form-item>
            <n-form-item label="패치 유형">
              <n-checkbox-group v-model:value="watchedForm.patch_types">
                <n-space>
                  <n-checkbox value="security" label="보안" />
                  <n-checkbox value="critical" label="긴급" />
                  <n-checkbox value="important" label="중요" />
                  <n-checkbox value="custom" label="커스텀" />
                </n-space>
              </n-checkbox-group>
            </n-form-item>
            <n-form-item label="정책 ID (선택)">
              <n-input v-model:value="watchedForm.policy_id" placeholder="Policy UUID" clearable />
            </n-form-item>
          </n-form>
          <template #footer>
            <n-space justify="end">
              <n-button @click="showWatchedModal = false">취소</n-button>
              <n-button type="primary" :loading="watchedSaving" @click="handleAddWatched">저장</n-button>
            </n-space>
          </template>
        </n-modal>
      </n-tab-pane>

      <!-- 델타 패치 탭 -->
      <n-tab-pane name="delta" tab="델타 패치">
        <n-card title="패치 간 델타 파일 생성">
          <n-alert type="info" style="margin-bottom: 16px">
            신규 패치와 이전 버전 패치 ID를 입력하면 bsdiff4 델타 파일을 생성하고 MinIO에 저장합니다.
            에이전트는 델타를 적용해 다운로드 크기를 줄입니다.
          </n-alert>
          <n-form label-placement="left" label-width="140" style="max-width: 480px">
            <n-form-item label="신규 패치 ID">
              <n-input v-model:value="deltaForm.patch_id" placeholder="새 버전 패치 UUID" />
            </n-form-item>
            <n-form-item label="기존 패치 ID (base)">
              <n-input v-model:value="deltaForm.base_patch_id" placeholder="이전 버전 패치 UUID" />
            </n-form-item>
          </n-form>
          <n-button type="primary" :loading="deltaGenerating" @click="handleGenerateDelta">
            델타 생성
          </n-button>
          <div v-if="deltaResult" style="margin-top: 16px">
            <n-alert type="success" title="델타 생성 완료">
              감소율: {{ deltaResult.reduction_pct }}% · 해시: {{ deltaResult.delta_hash?.slice(0, 16) }}…
            </n-alert>
          </div>
        </n-card>
      </n-tab-pane>

      <!-- 서명 공개키 탭 -->
      <n-tab-pane name="signing" tab="코드 서명">
        <n-card title="에이전트 서명 검증 공개키">
          <n-alert type="info" style="margin-bottom: 16px">
            이 공개키를 에이전트 배포 패키지에 번들하면, 에이전트가 패치 파일 서명을 검증합니다.
          </n-alert>
          <n-button @click="loadPublicKey" style="margin-bottom: 12px">공개키 조회</n-button>
          <n-code v-if="publicKey" :code="publicKey" language="text" word-wrap />
        </n-card>
      </n-tab-pane>

    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import api from '@/api/client'

const message = useMessage()
const activeTab = ref('ldap')

// ─── LDAP ────────────────────────────────────────────────────────────────────
const ldapStatus = ref<{ configured: boolean; connected: boolean }>({ configured: false, connected: false })
const ldapSyncing = ref(false)

async function loadLdapStatus() {
  try {
    const resp = await api.get('/admin/ldap/status')
    ldapStatus.value = resp.data
  } catch {}
}

async function handleLdapSync() {
  ldapSyncing.value = true
  try {
    const resp = await api.post('/admin/ldap/sync')
    message.success(`동기화 큐 등록 완료 (task: ${(resp.data as any).task_id?.slice(0, 8)})`)
  } catch {
    message.error('LDAP 동기화 실패')
  } finally {
    ldapSyncing.value = false
  }
}

// ─── 리포트 ──────────────────────────────────────────────────────────────────
interface ReportItem { name: string; size: number; last_modified: string | null }
const reports = ref<ReportItem[]>([])
const reportsLoading = ref(false)
const reportGenerating = ref(false)

const reportColumns = [
  { title: '파일명', key: 'name', ellipsis: { tooltip: true } },
  {
    title: '크기',
    key: 'size',
    width: 100,
    render: (row: ReportItem) => `${(row.size / 1024).toFixed(1)} KB`,
  },
  {
    title: '생성일',
    key: 'last_modified',
    width: 160,
    render: (row: ReportItem) =>
      row.last_modified ? new Date(row.last_modified).toLocaleString('ko-KR') : '-',
  },
  {
    title: '다운로드',
    key: 'download',
    width: 100,
    render: (row: ReportItem) =>
      h(NButton, { size: 'small', onClick: () => downloadReport(row.name) }, () => '다운로드'),
  },
]

async function loadReports() {
  reportsLoading.value = true
  try {
    const resp = await api.get('/admin/reports')
    reports.value = (resp.data as any).reports ?? []
  } finally {
    reportsLoading.value = false
  }
}

async function handleGenerateReport() {
  reportGenerating.value = true
  try {
    await api.post('/admin/reports/compliance')
    message.success('리포트 생성 중… 수초 후 목록을 새로고침하세요')
  } finally {
    reportGenerating.value = false
  }
}

async function downloadReport(reportName: string) {
  try {
    const resp = await api.get(`/admin/reports/${reportName}/download-url`)
    window.open((resp.data as any).download_url, '_blank')
  } catch {
    message.error('다운로드 URL 조회 실패')
  }
}

// ─── OpenVAS ──────────────────────────────────────────────────────────────────
const scanRunning = ref(false)

async function handleOpenvasScan() {
  scanRunning.value = true
  try {
    const resp = await api.post('/admin/openvas/scan')
    message.success(`OpenVAS 스캔 큐 등록 (task: ${(resp.data as any).task_id?.slice(0, 8)})`)
  } catch {
    message.error('OpenVAS 스캔 트리거 실패')
  } finally {
    scanRunning.value = false
  }
}

// ─── 자동 배포 감시 ────────────────────────────────────────────────────────────
interface WatchedProduct { id: string; product_id: string; target_type: string; patch_types: string[]; is_active: boolean }
const watchedProducts = ref<WatchedProduct[]>([])
const watchedLoading = ref(false)
const showWatchedModal = ref(false)
const watchedSaving = ref(false)
const watchedForm = ref({
  product_id: '',
  target_type: 'all',
  target_id: '',
  policy_id: '',
  patch_types: ['security', 'critical'] as string[],
})

const targetOptions = [
  { label: '전체', value: 'all' },
  { label: '그룹', value: 'group' },
  { label: '엔드포인트', value: 'endpoint' },
]

const watchedColumns = [
  { title: '제품 ID', key: 'product_id', ellipsis: { tooltip: true } },
  { title: '대상', key: 'target_type', width: 90 },
  {
    title: '패치 유형',
    key: 'patch_types',
    render: (row: WatchedProduct) => row.patch_types.join(', '),
  },
  {
    title: '삭제',
    key: 'actions',
    width: 80,
    render: (row: WatchedProduct) =>
      h(NButton, { size: 'small', type: 'error', onClick: () => handleDeleteWatched(row.id) }, () => '삭제'),
  },
]

async function loadWatched() {
  watchedLoading.value = true
  try {
    const resp = await api.get('/admin/watched-products')
    watchedProducts.value = resp.data
  } finally {
    watchedLoading.value = false
  }
}

async function handleAddWatched() {
  watchedSaving.value = true
  try {
    const payload: any = { ...watchedForm.value }
    if (payload.target_type === 'all') delete payload.target_id
    if (!payload.policy_id) delete payload.policy_id
    await api.post('/admin/watched-products', payload)
    message.success('감시 항목이 추가되었습니다')
    showWatchedModal.value = false
    watchedForm.value = { product_id: '', target_type: 'all', target_id: '', policy_id: '', patch_types: ['security', 'critical'] }
    loadWatched()
  } catch {
    message.error('추가 실패')
  } finally {
    watchedSaving.value = false
  }
}

async function handleDeleteWatched(id: string) {
  try {
    await api.delete(`/admin/watched-products/${id}`)
    message.success('비활성화되었습니다')
    loadWatched()
  } catch {
    message.error('삭제 실패')
  }
}

// ─── 델타 패치 ────────────────────────────────────────────────────────────────
const deltaForm = ref({ patch_id: '', base_patch_id: '' })
const deltaGenerating = ref(false)
const deltaResult = ref<any>(null)

async function handleGenerateDelta() {
  if (!deltaForm.value.patch_id || !deltaForm.value.base_patch_id) {
    message.warning('패치 ID를 모두 입력하세요')
    return
  }
  deltaGenerating.value = true
  deltaResult.value = null
  try {
    const resp = await api.post('/admin/delta-patches', deltaForm.value)
    deltaResult.value = resp.data
    message.success('델타 생성 완료')
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '델타 생성 실패')
  } finally {
    deltaGenerating.value = false
  }
}

// ─── 코드 서명 공개키 ──────────────────────────────────────────────────────────
const publicKey = ref('')

async function loadPublicKey() {
  try {
    const resp = await api.get('/admin/signing/public-key')
    publicKey.value = (resp.data as any).public_key ?? '공개키 없음'
  } catch {
    message.error('공개키 조회 실패')
  }
}

onMounted(() => {
  loadLdapStatus()
  loadReports()
  loadWatched()
})
</script>

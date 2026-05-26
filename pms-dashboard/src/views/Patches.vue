<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <n-space>
        <n-select
          v-model:value="filterSeverity"
          :options="severityOptions"
          placeholder="심각도 필터"
          clearable
          style="width: 140px"
          @update:value="loadPatches"
        />
        <n-select
          v-model:value="filterType"
          :options="typeOptions"
          placeholder="패치 유형"
          clearable
          style="width: 160px"
          @update:value="loadPatches"
        />
        <n-input
          v-model:value="filterCve"
          placeholder="CVE 검색 (예: CVE-2024-1234)"
          clearable
          style="width: 240px"
          @keyup.enter="loadPatches"
        />
      </n-space>
      <n-button type="primary" @click="showUpload = true">패치 업로드</n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="patches"
      :loading="loading"
      :pagination="{ pageSize: 20 }"
    />

    <!-- 업로드 모달 -->
    <n-modal v-model:show="showUpload" title="패치 파일 업로드" preset="card" style="width: 560px">
      <n-form :model="uploadForm" label-placement="left" label-width="100">
        <n-form-item label="제품 ID">
          <n-input v-model:value="uploadForm.product_id" placeholder="제품 UUID" />
        </n-form-item>
        <n-form-item label="버전">
          <n-input v-model:value="uploadForm.version" placeholder="1.2.3" />
        </n-form-item>
        <n-form-item label="제목">
          <n-input v-model:value="uploadForm.title" />
        </n-form-item>
        <n-form-item label="패치 유형">
          <n-select v-model:value="uploadForm.patch_type" :options="typeOptions" />
        </n-form-item>
        <n-form-item label="심각도">
          <n-select v-model:value="uploadForm.severity" :options="severityOptions" clearable />
        </n-form-item>
        <n-form-item label="배포일">
          <n-date-picker v-model:value="uploadForm.release_date" type="date" />
        </n-form-item>
        <n-form-item label="CVE">
          <n-input v-model:value="uploadForm.cve_ids" placeholder="CVE-2024-1234, CVE-2024-5678" />
        </n-form-item>
        <n-form-item label="파일">
          <n-upload :max="1" @change="onFileChange">
            <n-button>파일 선택</n-button>
          </n-upload>
        </n-form-item>
        <n-form-item label="재부팅 필요">
          <n-switch v-model:value="uploadForm.requires_reboot" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showUpload = false">취소</n-button>
          <n-button type="primary" :loading="uploading" @click="handleUpload">업로드</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, h, onMounted } from 'vue'
import { NTag, NButton, useMessage } from 'naive-ui'
import { patchApi, type Patch } from '@/api/patches'

const message = useMessage()
const patches = ref<Patch[]>([])
const loading = ref(false)
const showUpload = ref(false)
const uploading = ref(false)
const filterSeverity = ref<string | null>(null)
const filterType = ref<string | null>(null)
const filterCve = ref('')
let uploadFile: File | null = null

const uploadForm = reactive({
  product_id: '',
  version: '',
  title: '',
  patch_type: 'security',
  severity: null as string | null,
  release_date: null as number | null,
  cve_ids: '',
  requires_reboot: false,
})

const severityOptions = [
  { label: 'Critical', value: 'critical' },
  { label: 'High', value: 'high' },
  { label: 'Medium', value: 'medium' },
  { label: 'Low', value: 'low' },
]

const typeOptions = [
  { label: '보안 패치', value: 'security' },
  { label: '긴급', value: 'critical' },
  { label: '중요', value: 'important' },
  { label: '선택', value: 'optional' },
  { label: 'OS 누적', value: 'os_cumulative' },
  { label: '커스텀', value: 'custom' },
]

const severityColor: Record<string, 'error' | 'warning' | 'info' | 'default'> = {
  critical: 'error',
  high: 'error',
  medium: 'warning',
  low: 'info',
}

const columns = [
  { title: '제목', key: 'title', ellipsis: { tooltip: true } },
  {
    title: '심각도',
    key: 'severity',
    width: 90,
    render: (row: Patch) =>
      row.severity
        ? h(NTag, { type: severityColor[row.severity] ?? 'default', size: 'small' }, () => row.severity)
        : '-',
  },
  { title: '버전', key: 'version', width: 100 },
  {
    title: '유형',
    key: 'patch_type',
    width: 100,
    render: (row: Patch) => h(NTag, { size: 'small' }, () => row.patch_type),
  },
  {
    title: 'CVE',
    key: 'cve_ids',
    render: (row: Patch) =>
      row.cve_ids?.length ? row.cve_ids.slice(0, 2).join(', ') + (row.cve_ids.length > 2 ? '...' : '') : '-',
  },
  { title: '배포일', key: 'release_date', width: 110 },
  {
    title: '재부팅',
    key: 'requires_reboot',
    width: 80,
    render: (row: Patch) =>
      row.requires_reboot ? h(NTag, { type: 'warning', size: 'small' }, () => '필요') : '-',
  },
]

async function loadPatches() {
  loading.value = true
  try {
    const resp = await patchApi.list({
      severity: filterSeverity.value ?? undefined,
      patch_type: filterType.value ?? undefined,
      cve: filterCve.value || undefined,
    })
    patches.value = resp.data.items
  } finally {
    loading.value = false
  }
}

function onFileChange(data: any) {
  uploadFile = data.fileList[0]?.file ?? null
}

async function handleUpload() {
  if (!uploadFile) {
    message.error('파일을 선택해주세요')
    return
  }
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', uploadFile)
    form.append('product_id', uploadForm.product_id)
    form.append('version', uploadForm.version)
    form.append('title', uploadForm.title)
    form.append('patch_type', uploadForm.patch_type)
    form.append('release_date', uploadForm.release_date
      ? new Date(uploadForm.release_date).toISOString().split('T')[0]
      : new Date().toISOString().split('T')[0])
    if (uploadForm.severity) form.append('severity', uploadForm.severity)
    if (uploadForm.cve_ids) form.append('cve_ids', uploadForm.cve_ids)
    form.append('requires_reboot', String(uploadForm.requires_reboot))

    await patchApi.upload(form)
    message.success('패치 업로드 완료')
    showUpload.value = false
    loadPatches()
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '업로드 실패')
  } finally {
    uploading.value = false
  }
}

onMounted(loadPatches)
</script>

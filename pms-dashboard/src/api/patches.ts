import api from './client'

export interface Patch {
  id: string
  product_id: string
  version: string
  patch_type: string
  severity: string | null
  title: string
  cve_ids: string[] | null
  release_date: string
  file_size_bytes: number | null
  file_hash_sha256: string
  is_active: boolean
  requires_reboot: boolean
  created_at: string
}

export interface ComplianceItem {
  patch_id: string
  patch_title: string
  patch_version: string
  installed_version: string | null
  severity: string | null
  patch_type: string
  status: 'missing' | 'compliant' | 'newer'
}

export interface EndpointCompliance {
  endpoint_id: string
  total_patches: number
  missing: number
  compliant: number
  compliance_pct: number
  items: ComplianceItem[]
}

export interface ComplianceSummary {
  total_endpoints: number
  avg_compliance_pct: number
  endpoints: { endpoint_id: string; compliance_pct: number; missing: number }[]
}

export const patchApi = {
  list(params?: { page?: number; page_size?: number; patch_type?: string; severity?: string; cve?: string }) {
    return api.get<{ items: Patch[]; total: number; page: number; page_size: number }>('/patches', { params })
  },
  get(id: string) {
    return api.get<Patch>(`/patches/${id}`)
  },
  upload(form: FormData) {
    return api.post<Patch>('/patches', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  retire(id: string) {
    return api.delete(`/patches/${id}`)
  },
  affectedEndpoints(id: string) {
    return api.get(`/patches/${id}/affected-endpoints`)
  },
  endpointCompliance(endpointId: string) {
    return api.get<EndpointCompliance>(`/endpoints/${endpointId}/compliance`)
  },
  complianceSummary() {
    return api.get<ComplianceSummary>('/endpoints/compliance/summary')
  },
}

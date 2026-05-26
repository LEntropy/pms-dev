import api from './client'

export interface Endpoint {
  id: string
  hostname: string
  fqdn: string | null
  ip_address: string | null
  platform: string
  os_name: string | null
  os_version: string | null
  agent_version: string | null
  organization_id: string | null
  group_id: string | null
  status: string
  last_seen_at: string | null
  enrolled_at: string
  is_online: boolean
}

export interface EndpointListResponse {
  items: Endpoint[]
  total: number
  page: number
  page_size: number
}

export interface EndpointStats {
  by_status: Record<string, number>
  by_platform: Record<string, number>
  total: number
}

export interface SoftwareEntry {
  raw_name: string
  version: string | null
  vendor: string | null
  install_path: string | null
  detected_at: string
}

export interface ComplianceResult {
  endpoint_id: string
  total_patches: number
  compliant: number
  missing: number
  compliance_pct: number
  missing_patches: Array<{
    patch_id: string
    patch_name: string
    required_version: string
    severity: string
  }>
}

export const endpointApi = {
  list(params?: { page?: number; page_size?: number; status?: string; platform?: string }) {
    return api.get<EndpointListResponse>('/endpoints', { params })
  },
  get(id: string) {
    return api.get<Endpoint>(`/endpoints/${id}`)
  },
  stats() {
    return api.get<EndpointStats>('/endpoints/stats/summary')
  },
  software(id: string) {
    return api.get<{ endpoint_id: string; total: number; software: SoftwareEntry[] }>(`/endpoints/${id}/software`)
  },
  compliance(id: string) {
    return api.get<ComplianceResult>(`/endpoints/${id}/compliance`)
  },
  complianceSummary() {
    return api.get<any>('/endpoints/compliance/summary')
  },
  quarantine(id: string) {
    return api.post(`/endpoints/${id}/quarantine`)
  },
  decommission(id: string) {
    return api.delete(`/endpoints/${id}`)
  },
  createEnrollmentToken(data: { label?: string; organization_id?: string; expires_hours?: number }) {
    return api.post('/agent-admin/enrollment-tokens', data)
  },
}

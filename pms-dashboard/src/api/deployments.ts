import api from './client'

export interface Deployment {
  id: string
  patch_id: string
  policy_id: string | null
  initiated_by: string | null
  target_type: string
  target_id: string | null
  scheduled_at: string | null
  started_at: string | null
  completed_at: string | null
  status: string
  total_targets: number | null
  success_count: number
  failure_count: number
  created_at: string
}

export interface DeploymentResult {
  id: string
  endpoint_id: string
  status: string
  error_message: string | null
  exit_code: number | null
  download_started_at: string | null
  install_started_at: string | null
  completed_at: string | null
  rollback_snapshot_id: string | null
}

export interface Policy {
  id: string
  name: string
  description: string | null
  priority: number
  target_type: string
  target_id: string
  patch_types: string[]
  auto_install: boolean
  install_window: Record<string, any> | null
  max_concurrent: number
  bandwidth_limit_kbps: number | null
  rollback_on_failure: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export const deploymentApi = {
  list(params?: { status?: string; page?: number }) {
    return api.get<Deployment[]>('/deployments', { params })
  },
  get(id: string) {
    return api.get<Deployment>(`/deployments/${id}`)
  },
  create(data: {
    patch_id: string
    policy_id?: string
    target_type: string
    target_id?: string
    scheduled_at?: string
  }) {
    return api.post<Deployment>('/deployments', data)
  },
  results(id: string, status?: string) {
    return api.get<DeploymentResult[]>(`/deployments/${id}/results`, { params: { status } })
  },
  cancel(id: string) {
    return api.post(`/deployments/${id}/cancel`)
  },
  rollback(id: string) {
    return api.post(`/deployments/${id}/rollback`)
  },
  stats() {
    return api.get<{ by_status: Record<string, number> }>('/deployments/stats/summary')
  },
}

export const policyApi = {
  list() {
    return api.get<Policy[]>('/policies')
  },
  get(id: string) {
    return api.get<Policy>(`/policies/${id}`)
  },
  create(data: Partial<Policy>) {
    return api.post<Policy>('/policies', data)
  },
  update(id: string, data: Partial<Policy>) {
    return api.put<Policy>(`/policies/${id}`, data)
  },
  delete(id: string) {
    return api.delete(`/policies/${id}`)
  },
  simulate(policyId: string, patchId: string) {
    return api.post(`/policies/${policyId}/simulate?patch_id=${patchId}`)
  },
}

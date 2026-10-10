import type { FeatureCollection } from 'geojson'

export type FileStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED'

export interface FileInfo {
  id: string
  filename: string
  status: FileStatus
  crs: string | null
  feature_count: number | null
  error: string | null
}

export interface Measurement {
  feature_index: number
  geometry_type: string | null
  measurement_crs: string | null
  area_m2: number | null
  area_ha: number | null
  length_m: number | null
  length_km: number | null
  reason: string | null
  properties: Record<string, unknown>
}

export interface MeasurementPage {
  total: number
  items: Measurement[]
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail ?? `HTTP ${response.status}`)
  return body
}

export const uploadFile = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return request<FileInfo>('/api/files/', { method: 'POST', body: form })
}

export const getFile = (id: string) => request<FileInfo>(`/api/files/${id}/`)

// ponytail: shows the first 1000 features only; add paging controls if larger files matter.
export const getMeasurements = (id: string) =>
  request<MeasurementPage>(`/api/files/${id}/measurements/?limit=1000`)

export const getFeatures = (id: string) => request<FeatureCollection>(`/api/files/${id}/features/`)

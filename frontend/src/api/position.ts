import { request } from './client'
import type {
  PositionCreate,
  PositionUpdate,
  PositionResponse,
  PositionListResponse,
  JDCreate,
  JDResponse,
} from '@/types'

// ============ 岗位 CRUD ============

export async function createPosition(data: PositionCreate): Promise<PositionResponse> {
  return request<PositionResponse>('/positions', {
    method: 'POST',
    body: data,
  })
}

export async function listPositions(): Promise<PositionListResponse> {
  return request<PositionListResponse>('/positions')
}

export async function getPosition(name: string): Promise<PositionResponse> {
  return request<PositionResponse>(`/positions/${encodeURIComponent(name)}`)
}

export async function updatePosition(name: string, data: PositionUpdate): Promise<PositionResponse> {
  return request<PositionResponse>(`/positions/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: data,
  })
}

export async function deletePosition(name: string): Promise<void> {
  await request<unknown>(`/positions/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

// ============ JD 管理 ============

export async function addJD(positionName: string, data: JDCreate): Promise<JDResponse> {
  return request<JDResponse>(`/positions/${encodeURIComponent(positionName)}/jds`, {
    method: 'POST',
    body: data,
  })
}

export async function removeJD(positionName: string, jdId: string): Promise<void> {
  await request<unknown>(`/positions/${encodeURIComponent(positionName)}/jds/${jdId}`, {
    method: 'DELETE',
  })
}

export async function updateJD(positionName: string, jdId: string, data: JDCreate): Promise<JDResponse> {
  return request<JDResponse>(`/positions/${encodeURIComponent(positionName)}/jds/${jdId}`, {
    method: 'PUT',
    body: data,
  })
}

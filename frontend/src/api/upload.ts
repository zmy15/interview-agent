import { request } from './client'
import type { UploadResponse, ProjectUploadResponse, UploadRecord, UploadListResponse } from '@/types'

export async function uploadResume(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<UploadResponse>('/upload/resume', {
    method: 'POST',
    body: formData,
  })
}

export async function uploadCode(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<UploadResponse>('/upload/code', {
    method: 'POST',
    body: formData,
  })
}

export async function uploadProject(file: File): Promise<ProjectUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<ProjectUploadResponse>('/upload/project', {
    method: 'POST',
    body: formData,
  })
}

export async function listUploads(type?: string): Promise<UploadListResponse> {
  const params = type ? `?type=${type}` : ''
  return request<UploadListResponse>(`/upload/files${params}`)
}

export async function getUpload(id: string): Promise<UploadRecord> {
  return request<UploadRecord>(`/upload/files/${id}`)
}

export async function deleteUpload(id: string): Promise<void> {
  return request<void>(`/upload/files/${id}`, { method: 'DELETE' })
}

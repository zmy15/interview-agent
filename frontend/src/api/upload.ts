import { request } from './client'
import type { UploadResponse, ProjectUploadResponse } from '@/types'

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

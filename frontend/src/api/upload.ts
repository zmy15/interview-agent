import { request } from './client'
import type { UploadResponse } from '@/types'

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

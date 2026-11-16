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

/**
 * 上传要附加到提示词里的背景文档（txt / md 等，另支持 pdf / docx）。
 *
 * 后端只解析文本、不落库也不建索引：原文由前端本地保存，
 * 每轮对话随 prompt_documents 一起发回，由后端拼在系统提示词之后。
 */
export async function uploadPromptDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<UploadResponse>('/upload/document', {
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

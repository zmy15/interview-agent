import { request } from './client'
import type { KnowledgeUploadResponse, KnowledgeSearchRequest, KnowledgeSearchResponse } from '@/types'

export async function uploadKnowledge(
  file: File,
  positionName: string,
  docType: 'faq' | 'code' | 'project',
): Promise<KnowledgeUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('position_name', positionName)
  formData.append('doc_type', docType)
  return request<KnowledgeUploadResponse>('/knowledge/upload', {
    method: 'POST',
    body: formData,
  })
}

export async function listCollections(): Promise<{ collections: { name: string; count: number }[] }> {
  return request<{ collections: { name: string; count: number }[] }>('/knowledge/collections')
}

export async function deleteCollection(positionName: string): Promise<void> {
  await request<unknown>(`/knowledge/collections/${encodeURIComponent(positionName)}`, {
    method: 'DELETE',
  })
}

export async function searchKnowledge(
  query: string,
  positionName: string,
  topK: number = 3,
): Promise<KnowledgeSearchResponse> {
  return request<KnowledgeSearchResponse>('/knowledge/search', {
    method: 'POST',
    body: {
      query,
      position_name: positionName,
      top_k: topK,
    } satisfies KnowledgeSearchRequest,
  })
}

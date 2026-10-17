import { useState, useEffect, useCallback } from 'react'
import { getModels } from '@/api/chat'
import { useAppStore } from '@/stores/appStore'
import type { ModelInfo } from '@/types'

/**
 * 拉取可用模型列表。
 *
 * 模型列表由后端调用官方 GET /models 动态返回（不再写死在代码里），
 * 后端会按当前用户的 Key（数据库里加密保存的那把，或请求头传入的）
 * 返回该账号可用的模型 —— 因此这里不再需要前端携带 Key。
 */
export function useModels() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // API Key 变化后需要重新拉取：模型列表是按 Key 所属账号返回的。
  // 这里用掩码作为「Key 变过」的信号（掩码变了说明换了 Key）。
  const apiKeyHint = useAppStore((s) => s.apiKeyHint)

  const fetchModels = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getModels(!!apiKeyHint)
      setModels(res.models)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [apiKeyHint])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  return { models, loading, error, refetch: fetchModels }
}

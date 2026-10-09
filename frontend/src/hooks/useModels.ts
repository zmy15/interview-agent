import { useState, useEffect, useCallback } from 'react'
import { getModels } from '@/api/chat'
import { useAppStore } from '@/stores/appStore'
import type { ModelInfo } from '@/types'

/**
 * 拉取可用模型列表。
 *
 * 模型列表由后端调用官方 GET /models 动态返回（不再写死在代码里），
 * 这里会把用户配置的 API Key 一并带上，以便按该 Key 的账号列模型。
 */
export function useModels() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const apiKey = useAppStore((s) => s.apiKey)

  const fetchModels = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // apiKey 变化时强制刷新：模型列表是按 Key 的账号返回的
      const res = await getModels(!!apiKey)
      setModels(res.models)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [apiKey])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  return { models, loading, error, refetch: fetchModels }
}

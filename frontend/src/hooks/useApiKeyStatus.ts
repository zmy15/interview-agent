import { useCallback, useEffect, useRef, useState } from 'react'
import { settingsApi, type ApiKeyStatus } from '@/api/settings'
import { useAppStore } from '@/stores/appStore'

/**
 * API Key 状态（服务端权威） + 旧版本明文密钥的一次性迁移。
 *
 * 为什么需要这个 hook
 * ------------------
 * 密钥原先只存在浏览器 localStorage 里。桌面版 native 窗口是 pywebview，
 * ``private_mode`` 默认为 True，localStorage 每次重启都会被清空，表现为
 * 「配置过 API Key，重启就没了」。现在密钥加密存在服务端数据库，前端只在
 * 启动时拉一个掩码提示用于展示。
 *
 * 迁移逻辑
 * --------
 * appStore 的 persist migrate（v2 → v3）会把旧的明文 apiKey 搬到
 * ``legacyApiKey``。这里在启动时把它上传到服务端，随后立刻从内存清掉，
 * 避免明文继续留在本地。
 */
export function useApiKeyStatus() {
  const apiKeyHint = useAppStore((s) => s.apiKeyHint)
  const setApiKeyHint = useAppStore((s) => s.setApiKeyHint)
  const legacyApiKey = useAppStore((s) => s.legacyApiKey)
  const clearLegacyApiKey = useAppStore((s) => s.clearLegacyApiKey)
  const [loading, setLoading] = useState(true)
  const initedRef = useRef(false)

  /** 重新从服务端拉取状态（保存 / 清除后也可手动调用） */
  const refresh = useCallback(async (): Promise<ApiKeyStatus | null> => {
    try {
      const res = await settingsApi.getApiKey()
      setApiKeyHint(res.hint)
      return res
    } catch {
      // 拉不到就保持未配置状态：后端仍可能用 .env 的 Key 正常工作，
      // 没必要因为一个状态查询失败就打扰用户。
      return null
    } finally {
      setLoading(false)
    }
  }, [setApiKeyHint])

  useEffect(() => {
    // 只跑一次：React 18 的 StrictMode 会重复执行 effect
    if (initedRef.current) return
    initedRef.current = true

    void (async () => {
      const status = await refresh()

      if (legacyApiKey) {
        // 服务端还没有 Key 才迁移；已有则以服务端为准，不覆盖用户后来改的
        if (status && !status.configured) {
          try {
            const saved = await settingsApi.saveApiKey(legacyApiKey)
            setApiKeyHint(saved.hint)
          } catch {
            // 迁移失败不阻塞启动：用户可在弹窗里手动重新录入
          }
        }
        clearLegacyApiKey()
      }
    })()
  }, [refresh, legacyApiKey, setApiKeyHint, clearLegacyApiKey])

  return { apiKeyHint, loading, refresh }
}
/**
 * useSystemAudioListener — 系统音频监听（常驻开关驱动）
 *
 * 行为：
 *   开关打开 且 处于 AI 对话界面  → 自动开始监听，持续把识别结果送给回调
 *   开关关闭 或 离开对话界面      → 自动停止监听
 *
 * 为什么由「页面挂载」驱动而不是按钮：
 *   这是一个持续状态而不是一次性动作。用户打开开关后就该一直听着，
 *   不必每次进页面都手动点一下；离开页面则必须停掉，
 *   否则后台会一直占用音频设备、并持续往对话里灌内容。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { systemAudioApi } from '@/api/systemAudio'
import { useAppStore } from '@/stores/appStore'

const POLL_INTERVAL = 1000

export interface ListenerOptions {
  /** 是否处于 AI 对话界面（false 时自动停止） */
  active: boolean
  /** 每识别出一段完整的话就回调（final） */
  onText?: (text: string) => void
  /** 出错时回调 */
  onError?: (message: string) => void
}

export function useSystemAudioListener({ active, onText, onError }: ListenerOptions) {
  const enabled = useAppStore((s) => s.systemAudioEnabled)
  const device = useAppStore((s) => s.systemAudioDevice)

  const [listening, setListening] = useState(false)
  const [sttConnected, setSttConnected] = useState(false)
  const [sttError, setSttError] = useState<string | null>(null)

  const sinceRef = useRef(0)
  const timerRef = useRef<number | null>(null)
  const startingRef = useRef(false)

  // 回调放 ref，避免它们变化导致监听被反复重启
  const onTextRef = useRef(onText)
  const onErrorRef = useRef(onError)
  onTextRef.current = onText
  onErrorRef.current = onError

  /** 拉取增量转写并派发 */
  const poll = useCallback(async () => {
    try {
      const res = await systemAudioApi.transcript(sinceRef.current)

      if (res.lines.length > 0) {
        sinceRef.current = res.latest_seq
        for (const line of res.lines) {
          // 只把「断句完成」的文本交给上层：partial 是边说边变的，
          // 拿去提问会得到半句话。
          if (line.kind === 'final' && line.text.trim()) {
            onTextRef.current?.(line.text.trim())
          }
        }
      }

      setSttConnected(res.stt_connected)
      setSttError(res.stt_error ?? null)

      if (!res.running) {
        // 后端会话没了（服务重启等），停止本地轮询
        setListening(false)
      }
    } catch (err) {
      onErrorRef.current?.((err as Error).message)
    }
  }, [])

  // 开关 + 页面状态共同决定是否监听
  const shouldListen = enabled && active

  useEffect(() => {
    if (!shouldListen) return
    let cancelled = false

    const begin = async () => {
      if (startingRef.current) return
      startingRef.current = true
      try {
        // 重新开始时从 0 拉，避免漏掉刚启动就产生的行
        sinceRef.current = 0
        const res = await systemAudioApi.start({
          device_id: device || undefined,
        })
        if (cancelled) {
          // 启动过程中用户已经关掉了开关：立刻收尾
          void systemAudioApi.stop()
          return
        }
        setListening(true)
        setSttConnected(res.stt_connected)
        setSttError(res.stt_error ?? null)
      } catch (err) {
        if (!cancelled) {
          setListening(false)
          onErrorRef.current?.((err as Error).message)
        }
      } finally {
        startingRef.current = false
      }
    }

    void begin()

    return () => {
      cancelled = true
      // 停止轮询
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
      setListening(false)
      // 停止后端捕获（离开页面 / 关开关都要停，否则设备一直被占用）
      void systemAudioApi.stop().catch(() => {})
    }
  }, [shouldListen, device])

  // 监听中才轮询
  useEffect(() => {
    if (!listening) {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
      return
    }
    void poll()
    timerRef.current = window.setInterval(() => void poll(), POLL_INTERVAL)
    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [listening, poll])

  return { listening, sttConnected, sttError }
}
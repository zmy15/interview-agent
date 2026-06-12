/**
 * STT WebSocket 连接管理 — 流式语音识别
 */

import { useRef, useState, useCallback } from 'react'
import { STT_WS_BASE } from '@/api/stt'

export type STTConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'

interface UseSTTWebSocketOptions {
  onPartial?: (text: string) => void
  onFinal?: (text: string) => void
  onVAD?: (status: string) => void
  onError?: (error: string) => void
}

export function useSTTWebSocket(options: UseSTTWebSocketOptions = {}) {
  const [connectionState, setConnectionState] = useState<STTConnectionState>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptRef = useRef(0)
  const maxReconnect = 3

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setConnectionState('connecting')
    const ws = new WebSocket(`${STT_WS_BASE}/stream`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionState('connected')
      reconnectAttemptRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        switch (msg.type) {
          case 'partial':
            options.onPartial?.(msg.text || '')
            break
          case 'final':
            options.onFinal?.(msg.text || '')
            break
          case 'vad':
            options.onVAD?.(msg.status || '')
            break
          case 'error':
            options.onError?.(msg.message || '未知错误')
            break
        }
      } catch {
        // 忽略非 JSON 消息
      }
    }

    ws.onerror = () => {
      setConnectionState('error')
    }

    ws.onclose = () => {
      setConnectionState('disconnected')
      // 自动重连
      if (reconnectAttemptRef.current < maxReconnect) {
        reconnectAttemptRef.current++
        const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 5000)
        setTimeout(connect, delay)
      }
    }
  }, [options])

  const disconnect = useCallback(() => {
    reconnectAttemptRef.current = maxReconnect // 禁止重连
    wsRef.current?.close()
    wsRef.current = null
    setConnectionState('disconnected')
  }, [])

  const sendAudioFrame = useCallback((frame: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(frame)
    }
  }, [])

  const sendFlush = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'flush' }))
    }
  }, [])

  const sendReset = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'reset' }))
    }
  }, [])

  return { connectionState, connect, disconnect, sendAudioFrame, sendFlush, sendReset }
}

/**
 * 语音服务可用性检测 Hook — 轮询 STT/TTS 健康检查
 */

import { useState, useEffect, useCallback } from 'react'
import { checkSTTHealth } from '@/api/stt'
import { checkTTSHealth } from '@/api/tts'

interface VoiceAvailability {
  sttAvailable: boolean
  ttsAvailable: boolean
  voiceAvailable: boolean
  checking: boolean
  checkNow: () => void
}

const POLL_INTERVAL = 30000 // 30s

export function useVoiceAvailability(): VoiceAvailability {
  const [sttAvailable, setSttAvailable] = useState(false)
  const [ttsAvailable, setTtsAvailable] = useState(false)
  const [checking, setChecking] = useState(true)

  const check = useCallback(async () => {
    setChecking(true)
    const [sttOk, ttsOk] = await Promise.all([
      checkSTTHealth(),
      checkTTSHealth(),
    ])
    setSttAvailable(sttOk)
    setTtsAvailable(ttsOk)
    setChecking(false)
  }, [])

  useEffect(() => {
    check()
    const interval = setInterval(check, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [check])

  return {
    sttAvailable,
    ttsAvailable,
    voiceAvailable: sttAvailable || ttsAvailable,
    checking,
    checkNow: check,
  }
}

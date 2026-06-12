/**
 * 录音 Hook — 输出 16kHz PCM 帧，支持指定麦克风设备
 */

import { useRef, useState, useCallback } from 'react'

export type RecorderState = 'idle' | 'recording' | 'processing'

export interface AudioDevice {
  deviceId: string
  label: string
  kind: string
}

/** 枚举可用的音频输入设备 */
export async function getAudioDevices(): Promise<AudioDevice[]> {
  try { await navigator.mediaDevices.getUserMedia({ audio: true }) } catch { /* 权限 */ }
  const devices = await navigator.mediaDevices.enumerateDevices()
  return devices
    .filter((d) => d.kind === 'audioinput')
    .map((d) => ({
      deviceId: d.deviceId,
      label: d.label || `麦克风 ${d.deviceId.slice(0, 8)}`,
      kind: d.kind,
    }))
}

interface UseVoiceRecorderOptions {
  deviceId?: string
  onAudioFrame?: (frame: ArrayBuffer) => void
}

interface UseVoiceRecorderReturn {
  startRecording: () => Promise<void>
  stopRecording: () => Promise<Blob | null>
  state: RecorderState
  audioLevel: number
  error: string | null
}

export function useVoiceRecorder(
  opts?: UseVoiceRecorderOptions,
): UseVoiceRecorderReturn {
  const { onAudioFrame, deviceId } = opts || {}
  const [state, setState] = useState<RecorderState>('idle')
  const [audioLevel, setAudioLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const streamRef = useRef<MediaStream | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const levelIntervalRef = useRef<number | null>(null)

  const startRecording = useCallback(async () => {
    try {
      setError(null)
      chunksRef.current = []

      // 获取麦克风（支持指定设备）
      const constraints: MediaStreamConstraints = {
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          ...(deviceId && deviceId !== 'default' ? { deviceId: { exact: deviceId } } : {}),
        },
      }
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream

      // 设置音频分析器（音量可视化）
      const audioCtx = new AudioContext({ sampleRate: 16000 })
      audioContextRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyserRef.current = analyser

      // 音量检测
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      levelIntervalRef.current = window.setInterval(() => {
        analyser.getByteFrequencyData(dataArray)
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length
        setAudioLevel(avg / 255)
      }, 100)

      // MediaRecorder（用于兜底批量模式）
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
          // 也发送 PCM 帧给 WebSocket
          if (onAudioFrame) {
            e.data.arrayBuffer().then((buf) => {
              onAudioFrame(buf)
            })
          }
        }
      }

      recorder.start(100) // 每 100ms 发送一个 chunk
      setState('recording')
    } catch (err) {
      const msg = err instanceof DOMException && err.name === 'NotAllowedError'
        ? '麦克风权限被拒绝，请在浏览器设置中允许访问麦克风'
        : `录音启动失败: ${err}`
      setError(msg)
      setState('idle')
    }
  }, [onAudioFrame, deviceId])

  const stopRecording = useCallback(async (): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current
      if (!recorder || recorder.state === 'inactive') {
        cleanup()
        setState('idle')
        resolve(null)
        return
      }

      setState('processing')

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType })
        cleanup()
        setState('idle')
        resolve(blob)
      }

      recorder.stop()
    })
  }, [])

  const cleanup = () => {
    if (levelIntervalRef.current) {
      clearInterval(levelIntervalRef.current)
      levelIntervalRef.current = null
    }
    if (analyserRef.current) {
      analyserRef.current.disconnect()
      analyserRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    mediaRecorderRef.current = null
    setAudioLevel(0)
  }

  return { startRecording, stopRecording, state, audioLevel, error }
}

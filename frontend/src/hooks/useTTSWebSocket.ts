/**
 * TTS WebSocket 连接 + 流式播放管理
 */

import { useRef, useState, useCallback } from 'react'
import { TTS_WS_BASE } from '@/api/tts'

interface UseTTSWebSocketOptions {
  onDone?: () => void
  onError?: (error: string) => void
}

export function useTTSWebSocket(options: UseTTSWebSocketOptions = {}) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [currentSentence, setCurrentSentence] = useState(0)
  const [totalSentences, setTotalSentences] = useState(0)

  const wsRef = useRef<WebSocket | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const nextStartTimeRef = useRef(0)
  const queueRef = useRef<AudioBuffer[]>([])

  const ensureAudioContext = () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext({ sampleRate: 22050 })
    }
    if (audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume()
    }
    return audioContextRef.current
  }

  /**
   * 流式合成 — 逐句发送文本，实时播放 PCM chunk
   */
  const synthesizeStream = useCallback(async (sentences: string[]) => {
    if (sentences.length === 0) return

    setIsLoading(true)
    setIsPlaying(true)
    setTotalSentences(sentences.length)
    setCurrentSentence(0)
    queueRef.current = []
    nextStartTimeRef.current = 0

    const ctx = ensureAudioContext()

    const ws = new WebSocket(`${TTS_WS_BASE}/stream`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws
    let sentenceIdx = 0

    ws.onopen = () => {
      // 发送第一句
      if (sentences[0]) {
        ws.send(JSON.stringify({ text: sentences[0] }))
        sentenceIdx = 1
      }
    }

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        // PCM 音频 chunk → 解码 → 加入播放队列
        try {
          const pcmData = event.data
          // 创建 WAV buffer（添加 WAV 头以便 decodeAudioData）
          const wavBuffer = pcmToWav(pcmData, 22050)
          const audioBuffer = await ctx.decodeAudioData(wavBuffer)
          queueRef.current.push(audioBuffer)

          // 排期播放
          const source = ctx.createBufferSource()
          source.buffer = audioBuffer
          source.connect(ctx.destination)
          const startTime = Math.max(ctx.currentTime, nextStartTimeRef.current)
          source.start(startTime)
          nextStartTimeRef.current = startTime + audioBuffer.duration

          setCurrentSentence((prev) => prev + 1)
        } catch {
          // 解码失败，跳过
        }
      } else {
        try {
          const msg = JSON.parse(event.data as string)
          if (msg.type === 'done') {
            setIsPlaying(false)
            setIsLoading(false)
            options.onDone?.()
          } else if (msg.type === 'error') {
            options.onError?.(msg.message || 'TTS error')
            setIsPlaying(false)
            setIsLoading(false)
          }
        } catch {
          // ignore
        }
      }
    }

    // 逐句发送后续文本
    const sendNext = () => {
      if (sentenceIdx < sentences.length && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ text: sentences[sentenceIdx] }))
        sentenceIdx++
      } else if (sentenceIdx >= sentences.length && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'eos' }))
      }
    }

    ws.onmessage = (event) => {
      // 重写以加入 sendNext 逻辑
      ;(async () => {
        if (event.data instanceof ArrayBuffer) {
          try {
            const wavBuffer = pcmToWav(event.data, 22050)
            const audioBuffer = await ctx.decodeAudioData(wavBuffer)
            queueRef.current.push(audioBuffer)

            const source = ctx.createBufferSource()
            source.buffer = audioBuffer
            source.connect(ctx.destination)
            const startTime = Math.max(ctx.currentTime, nextStartTimeRef.current)
            source.start(startTime)
            nextStartTimeRef.current = startTime + audioBuffer.duration

            setCurrentSentence((prev) => {
              const next = prev + 1
              return next
            })

            // 播放当前句时发送下一句
            sendNext()
          } catch {
            sendNext()
          }
        } else {
          try {
            const msg = JSON.parse(event.data as string)
            if (msg.type === 'done') {
              setIsPlaying(false)
              setIsLoading(false)
              options.onDone?.()
            } else if (msg.type === 'error') {
              options.onError?.(msg.message || '')
              setIsPlaying(false)
              setIsLoading(false)
            }
          } catch {
            // ignore
          }
        }
      })()
    }

    ws.onerror = () => {
      options.onError?.('TTS WebSocket 连接失败')
      setIsPlaying(false)
      setIsLoading(false)
    }
  }, [options])

  const stop = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }
    setIsPlaying(false)
    setIsLoading(false)
    queueRef.current = []
  }, [])

  return { synthesizeStream, stop, isPlaying, isLoading, currentSentence, totalSentences }
}

/**
 * PCM Int16 → WAV ArrayBuffer（添加 44 字节 WAV 头）
 */
function pcmToWav(pcmData: ArrayBuffer, sampleRate: number): ArrayBuffer {
  const numChannels = 1
  const bitsPerSample = 16
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8)
  const blockAlign = numChannels * (bitsPerSample / 8)
  const dataSize = pcmData.byteLength
  const headerSize = 44

  const buffer = new ArrayBuffer(headerSize + dataSize)
  const view = new DataView(buffer)

  // RIFF header
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeString(view, 8, 'WAVE')
  // fmt chunk
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bitsPerSample, true)
  // data chunk
  writeString(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  // 复制 PCM 数据
  new Uint8Array(buffer, headerSize, dataSize).set(new Uint8Array(pcmData))

  return buffer
}

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

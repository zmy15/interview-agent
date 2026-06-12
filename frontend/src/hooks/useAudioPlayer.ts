/**
 * 音频播放 Hook — 支持完整播放 + 流式播放队列
 */

import { useRef, useState, useCallback } from 'react'

export function useAudioPlayer() {
  const [isPlaying, setIsPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const cacheRef = useRef<Map<string, string>>(new Map()) // text → blob URL

  /**
   * 播放完整音频 Blob
   */
  const play = useCallback(async (audioBlob: Blob, cacheKey?: string): Promise<void> => {
    // 检查缓存
    if (cacheKey && cacheRef.current.has(cacheKey)) {
      const url = cacheRef.current.get(cacheKey)!
      playUrl(url)
      return
    }

    const url = URL.createObjectURL(audioBlob)
    if (cacheKey) {
      cacheRef.current.set(cacheKey, url)
    }

    playUrl(url)
  }, [])

  const playUrl = (url: string) => {
    stop()
    const audio = new Audio(url)
    audioRef.current = audio
    audio.onplay = () => setIsPlaying(true)
    audio.onended = () => setIsPlaying(false)
    audio.onerror = () => setIsPlaying(false)
    audio.play().catch(() => setIsPlaying(false))
  }

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current = null
    }
    setIsPlaying(false)
  }, [])

  return { play, stop, isPlaying }
}

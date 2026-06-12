/**
 * TTS 语音合成 API — WebSocket 流式 + HTTP 批量兜底
 */

const TTS_WS_BASE = (() => {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/api/tts`
})()

const TTS_HTTP_BASE = '/api/tts'

/**
 * HTTP 批量合成（兜底方案）
 */
export async function synthesizeSpeech(text: string): Promise<Blob> {
  const resp = await fetch(`${TTS_HTTP_BASE}/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }))
    throw new Error(err.error || err.detail || `合成失败: HTTP ${resp.status}`)
  }

  return resp.blob()
}

/**
 * 检查 TTS 服务健康状态
 */
export async function checkTTSHealth(): Promise<boolean> {
  try {
    const resp = await fetch(`${TTS_HTTP_BASE}/health`, { signal: AbortSignal.timeout(5000) })
    return resp.ok
  } catch {
    return false
  }
}

export { TTS_WS_BASE }

/**
 * STT 语音识别 API — WebSocket 流式 + HTTP 批量兜底
 */

const STT_WS_BASE = (() => {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/api/stt`
})()

const STT_HTTP_BASE = '/api/stt'

/**
 * HTTP 批量转录（兜底方案）
 */
export async function transcribeAudio(audioBlob: Blob): Promise<string> {
  const formData = new FormData()
  formData.append('file', audioBlob, 'recording.webm')

  const resp = await fetch(`${STT_HTTP_BASE}/transcribe`, {
    method: 'POST',
    body: formData,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }))
    throw new Error(err.error || err.detail || `转录失败: HTTP ${resp.status}`)
  }

  const data = await resp.json()
  return data.text || ''
}

/**
 * 检查 STT 服务健康状态
 */
export async function checkSTTHealth(): Promise<boolean> {
  try {
    const resp = await fetch(`${STT_HTTP_BASE}/health`, { signal: AbortSignal.timeout(5000) })
    return resp.ok
  } catch {
    return false
  }
}

export { STT_WS_BASE }

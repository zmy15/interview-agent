/**
 * HTTP 客户端 — fetch 实现（无外部依赖）
 * 自动注入 Bearer Token，401 时触发刷新
 * 与项目中 client.ts 一致，使用原生 fetch API
 */

const BASE_URL = '/api'

// ── 工具函数 ──

function _getToken(): string | null {
  try {
    const stored = localStorage.getItem('interview-agent-auth')
    if (stored) {
      const parsed = JSON.parse(stored)
      return parsed?.state?.accessToken || null
    }
  } catch { /* ignore */ }
  return null
}

function _getRefreshToken(): string | null {
  try {
    const stored = localStorage.getItem('interview-agent-auth')
    if (stored) {
      const parsed = JSON.parse(stored)
      return parsed?.state?.refreshToken || null
    }
  } catch { /* ignore */ }
  return null
}

function _saveTokens(accessToken: string, refreshToken: string) {
  try {
    const stored = localStorage.getItem('interview-agent-auth')
    if (stored) {
      const parsed = JSON.parse(stored)
      parsed.state.accessToken = accessToken
      parsed.state.refreshToken = refreshToken
      localStorage.setItem('interview-agent-auth', JSON.stringify(parsed))
    }
  } catch { /* ignore */ }
}

async function _tryRefreshToken(): Promise<boolean> {
  const refreshToken = _getRefreshToken()
  if (!refreshToken) return false
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (res.ok) {
      const data = await res.json()
      _saveTokens(data.access_token, data.refresh_token)
      return true
    }
  } catch { /* ignore */ }
  localStorage.removeItem('interview-agent-auth')
  return false
}

// ── 核心请求函数 ──

interface FetchClientOptions {
  params?: Record<string, string | number | undefined>
}

type FetchClientResponse<T> = { data: T }

async function _request<T>(
  method: string,
  url: string,
  body?: unknown,
  options?: FetchClientOptions,
): Promise<FetchClientResponse<T>> {
  let fullUrl = `${BASE_URL}${url}`
  if (options?.params) {
    // 过滤掉 undefined / null 值，避免 "search=undefined" 这种无效参数
    const clean: Record<string, string> = {}
    for (const [k, v] of Object.entries(options.params)) {
      if (v !== undefined && v !== null && v !== '') {
        clean[k] = String(v)
      }
    }
    if (Object.keys(clean).length > 0) {
      const sp = new URLSearchParams(clean)
      fullUrl += `?${sp.toString()}`
    }
  }

  const headers: Record<string, string> = {}
  const token = _getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let reqBody: BodyInit | null = null
  if (body !== undefined && body !== null) {
    headers['Content-Type'] = 'application/json'
    reqBody = JSON.stringify(body)
  }

  let res = await fetch(fullUrl, { method, headers, body: reqBody })

  // 401 自动刷新
  if (res.status === 401) {
    const refreshed = await _tryRefreshToken()
    if (refreshed) {
      const newToken = _getToken()
      if (newToken) {
        headers['Authorization'] = `Bearer ${newToken}`
      }
      res = await fetch(fullUrl, { method, headers, body: reqBody })
    }
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const errBody = await res.json()
      detail = errBody.detail || detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }

  // 204 No Content
  if (res.status === 204) {
    return { data: undefined as unknown as T }
  }

  const json = await res.json()
  return { data: json as T }
}

// ── 对外接口（与 axios 风格一致） ──

export const apiClient = {
  get: <T>(url: string, options?: FetchClientOptions) =>
    _request<T>('GET', url, undefined, options),

  post: <T>(url: string, data?: unknown, options?: FetchClientOptions) =>
    _request<T>('POST', url, data, options),

  put: <T>(url: string, data?: unknown, options?: FetchClientOptions) =>
    _request<T>('PUT', url, data, options),

  delete: <T>(url: string, options?: FetchClientOptions) =>
    _request<T>('DELETE', url, undefined, options),
}

export { BASE_URL }


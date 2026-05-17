const BASE_URL = '/api'

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  params?: Record<string, string>
}

class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // ignore parse error
    }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { params, body, ...fetchOptions } = options

  let fullUrl = `${BASE_URL}${url}`
  if (params) {
    const searchParams = new URLSearchParams(params)
    fullUrl += `?${searchParams.toString()}`
  }

  const headers: Record<string, string> = {}
  let requestBody: BodyInit | null = null

  if (body instanceof FormData) {
    requestBody = body
  } else if (body !== undefined && body !== null) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }

  const response = await fetch(fullUrl, {
    ...fetchOptions,
    method: fetchOptions.method || 'GET',
    headers: {
      ...headers,
      ...((fetchOptions.headers as Record<string, string>) || {}),
    },
    body: requestBody,
  })

  return handleResponse<T>(response)
}

export { ApiError, BASE_URL }

const BASE = import.meta.env.VITE_API_URL ?? '/api'
const TOKEN_KEY = 'classtrack.token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function storage(): Storage[] {
  const out: Storage[] = []
  try {
    out.push(localStorage, sessionStorage)
  } catch {
    // storage blocked (private mode etc.) — token lives only in memory
  }
  return out
}

let memoryToken: string | null = null

export function getToken(): string | null {
  if (memoryToken) return memoryToken
  for (const s of storage()) {
    const t = s.getItem(TOKEN_KEY)
    if (t) return (memoryToken = t)
  }
  return null
}

export function setToken(token: string | null, remember = true) {
  memoryToken = token
  for (const s of storage()) s.removeItem(TOKEN_KEY)
  if (token) {
    try {
      ;(remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token)
    } catch {
      /* memory only */
    }
  }
}

let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = d.loc?.filter((l) => l !== 'body').join('.')
        const msg = (d.msg ?? '').replace(/^Value error, /, '')
        return field ? `${field}: ${msg}` : msg
      })
      .join('; ')
  }
  return fallback
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    ...rest,
    headers: {
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized()
    throw new ApiError(res.status, errorMessage(body, `Request failed (${res.status})`))
  }
  return body as T
}

export async function login(email: string, password: string): Promise<string> {
  const form = new URLSearchParams({ username: email, password })
  const { access_token } = await api<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: form,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return access_token
}

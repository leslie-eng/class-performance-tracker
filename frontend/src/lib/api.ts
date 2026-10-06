/** VITE_API_URL without a trailing slash; '/api' (the Vite dev proxy) when unset or blank. */
function apiBase(raw: string | undefined): string {
  const url = raw?.trim().replace(/\/+$/, '')
  if (!url) return '/api'
  // "classtrack-api.onrender.com" without a scheme would resolve against the frontend's own origin.
  return /^(https?:)?\/\//.test(url) || url.startsWith('/') ? url : `https://${url}`
}

const BASE = apiBase(import.meta.env.VITE_API_URL)
const TOKEN_KEY = 'classtrack.token'

if (import.meta.env.PROD && BASE === '/api') {
  console.warn(
    '[api] VITE_API_URL was not set when this build was made, so requests go to /api on the frontend host. ' +
      'Set VITE_API_URL to the API URL and rebuild.',
  )
}

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
  const url = `${BASE}${path}`
  const method = (rest.method ?? 'GET').toUpperCase()

  let res: Response
  try {
    res = await fetch(url, {
      ...rest,
      headers: {
        ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    })
  } catch (err) {
    // fetch only rejects when no response is readable: offline, DNS failure, or blocked by CORS.
    console.error(`[api] ${method} ${url} failed before a response (network or CORS)`, err)
    throw new ApiError(
      0,
      `Could not reach the API at ${BASE}. Check your connection, that VITE_API_URL is right, ` +
        `and that the API's CORS_ORIGINS includes ${window.location.origin}.`,
    )
  }

  if (res.status === 204) return undefined as T
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    // not JSON; handled below
  }

  if (!res.ok) {
    console.error(`[api] ${method} ${url} -> ${res.status}`, body ?? text.slice(0, 300))
    if (res.status === 401 && token) onUnauthorized()
    throw new ApiError(res.status, errorMessage(body, res.statusText || 'Request failed'))
  }
  if (body === null && text) {
    // A 2xx HTML page is the frontend's index.html: the request never reached the API.
    console.error(`[api] ${method} ${url} -> ${res.status} but the response is not JSON`, text.slice(0, 300))
    throw new ApiError(
      res.status,
      `The API URL returned a web page instead of JSON, so the request never reached the API. ` +
        `VITE_API_URL is probably unset or points at the frontend (current: ${BASE}). Set it and rebuild.`,
    )
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

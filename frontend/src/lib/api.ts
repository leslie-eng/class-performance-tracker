/** VITE_API_URL without a trailing slash; '/api' (the Vite dev proxy) when unset or blank. */
// Exported for unit tests; the module is the single place that resolves the base URL.
export function apiBase(raw: string | undefined): string {
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
      ; (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token)
    } catch {
      /* memory only */
    }
  }
}

let onUnauthorized: () => void = () => { }
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

// Exported for unit tests; unwraps FastAPI's `detail` (string or validation array).
export function errorMessage(body: unknown, fallback: string): string {
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

/** True when `base` resolves to the frontend's own origin: VITE_API_URL unset (the /api dev proxy) or set to the site. */
export function pointsAtFrontend(base: string, frontendOrigin: string): boolean {
  try {
    return new URL(base, frontendOrigin).origin === frontendOrigin
  } catch {
    return false
  }
}

/**
 * Message for a 2xx response that isn't JSON. Only blame VITE_API_URL when it really points at the
 * frontend; a separate API host answering with HTML is almost always still starting up (Render's
 * free tier sleeps when idle and can answer with its own page while it wakes).
 */
export function nonJsonMessage(base: string, frontendOrigin: string): string {
  return pointsAtFrontend(base, frontendOrigin)
    ? `The API URL returned a web page instead of JSON, so the request never reached the API. ` +
    `VITE_API_URL is probably unset or points at the frontend (current: ${base}). Set it and rebuild.`
    : `The API at ${base} answered with a web page instead of JSON. It is probably still starting up ` +
    `(the free hosting tier sleeps when idle); try again in a minute.`
}

const COLD_START_RETRY_MS = 5000

/**
 * `T` defaults to `void`: a call with no explicit type argument, such as a DELETE, is treated
 * as a call whose response is deliberately unused. Call sites that do use the body must name
 * its type, so an unknown response can no longer be read as a typed value by accident.
 */
export async function api<T = void>(path: string, init: RequestInit & { json?: unknown } = {}, attempt = 0): Promise<T> {
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
    console.error(`[api] ${method} ${url} -> ${res.status} but the response is not JSON`, text.slice(0, 300))
    const misconfigured = pointsAtFrontend(BASE, window.location.origin)
    if (!misconfigured && attempt === 0 && (method === 'GET' || method === 'HEAD')) {
      // Probably a sleeping API waking up: one quiet retry (only for reads, which are safe to repeat).
      await new Promise((resolve) => setTimeout(resolve, COLD_START_RETRY_MS))
      return api<T>(path, init, attempt + 1)
    }
    // 503 when the API is starting, so React Query's 5xx retry also kicks in for page loads.
    throw new ApiError(misconfigured ? res.status : 503, nonJsonMessage(BASE, window.location.origin))
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

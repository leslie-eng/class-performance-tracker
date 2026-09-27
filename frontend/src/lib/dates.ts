import type { Challenge } from './types'

const DAY_MS = 86_400_000

/** Parses a YYYY-MM-DD string as a UTC date (no timezone drift). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

export function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export function addDays(iso: string, n: number): string {
  return isoDay(new Date(parseDay(iso).getTime() + n * DAY_MS))
}

export function daysBetween(a: string, b: string): number {
  return Math.round((parseDay(b).getTime() - parseDay(a).getTime()) / DAY_MS)
}

/** Day number in the challenge for `today` (day 1 = start_date). May be <1 or >total_days. */
export function dayNumber(challenge: Challenge, today: string): number {
  return daysBetween(challenge.start_date, today) + 1
}

export function dateForDay(challenge: Challenge, day: number): string {
  return addDays(challenge.start_date, day - 1)
}

/** Days that have fully or partially elapsed in the challenge, up to today. */
export function elapsedDays(challenge: Challenge, today: string): number {
  return Math.max(0, Math.min(dayNumber(challenge, today), challenge.total_days))
}

/** Seconds until midnight in the given IANA timezone (the backend's "today" boundary). */
export function secondsToMidnight(timezone: string, now = new Date()): number {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: timezone,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now)
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0)
  return 86_400 - (get('hour') * 3600 + get('minute') * 60 + get('second'))
}

export function formatCountdown(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':')
}

export function relativeTime(iso: string, now = Date.now()): string {
  const diff = Math.round((now - new Date(iso).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86_400) return `${Math.floor(diff / 3600)}h ago`
  const days = Math.floor(diff / 86_400)
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function shortDate(iso: string): string {
  return parseDay(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export function greeting(timezone: string): string {
  const hour = Number(
    new Intl.DateTimeFormat('en-GB', { timeZone: timezone, hour: '2-digit', hourCycle: 'h23' }).format(new Date()),
  )
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

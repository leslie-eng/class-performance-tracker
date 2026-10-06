import { ApiError } from '../lib/api'
import { initials } from '../lib/format'
import type { ReactNode } from 'react'

export function Icon({ name, className = '', filled = false }: { name: string; className?: string; filled?: boolean }) {
  return (
    <span aria-hidden className={`material-symbols-outlined select-none ${filled ? 'filled' : ''} ${className}`}>
      {name}
    </span>
  )
}

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="#2563eb" />
      <path d="M9 11l5 5-5 5" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16 21h7" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`font-semibold tracking-tight ${className}`}>
      Class<span className="text-primary-container">Track</span>
    </span>
  )
}

export function StreakPill({ days, className = '' }: { days: number; className?: string }) {
  return (
    <span className={`pill bg-streak-bg font-bold text-streak-text ${className}`}>
      <Icon name="local_fire_department" filled className="text-[16px] text-streak" />
      {days} {days === 1 ? 'Day' : 'Days'}
    </span>
  )
}

const AVATAR_TINTS = [
  'bg-primary-fixed text-primary',
  'bg-secondary-container/60 text-secondary',
  'bg-tertiary-fixed text-tertiary',
  'bg-surface-container-highest text-on-surface',
]

export function Avatar({ name, id, size = 36, ring }: { name: string; id: number; size?: number; ring?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-mono font-bold ${AVATAR_TINTS[id % AVATAR_TINTS.length]} ${ring ?? ''}`}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
    >
      {initials(name)}
    </span>
  )
}

/** SVG ring gauge; value/max. */
export function ScoreRing({
  value,
  max = 10,
  size = 132,
  stroke = 10,
  color = '#2563eb',
  label,
  sub,
}: {
  value: number
  max?: number
  size?: number
  stroke?: number
  color?: string
  label?: ReactNode
  sub?: ReactNode
}) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(1, value / max))
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct)}
          style={{ transition: 'stroke-dashoffset 600ms ease-out' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono leading-none font-bold text-ink" style={{ fontSize: size * 0.26 }}>
          {label ?? value}
        </span>
        {sub && <span className="mt-1 font-mono text-label-sm text-on-surface-variant">{sub}</span>}
      </div>
    </div>
  )
}

export function ProgressBar({ value, className = 'bg-primary-container', track = 'bg-surface-container' }: { value: number; className?: string; track?: string }) {
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full ${track}`}>
      <div className={`h-full rounded-full ${className}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

export function Spinner({ className = '' }: { className?: string }) {
  return <Icon name="progress_activity" className={`animate-spin ${className}`} />
}

export function PageLoader() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-on-surface-variant">
      <Spinner className="text-[32px]" />
    </div>
  )
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null
  const text = error instanceof Error ? error.message : String(error)
  // status 0 means no response at all (network/CORS), so there's no code to show
  const msg = error instanceof ApiError && error.status ? `Error ${error.status}: ${text}` : text
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg bg-error-container px-3 py-2 text-body-md text-on-error-container">
      <Icon name="error" className="text-[18px]" />
      <span>{msg}</span>
    </div>
  )
}

export function EmptyState({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-container-low text-primary-container">
        <Icon name={icon} />
      </span>
      <p className="font-semibold text-ink">{title}</p>
      {children && <div className="max-w-md text-body-md text-on-surface-variant">{children}</div>}
    </div>
  )
}

export function StatCard({
  label,
  icon,
  iconClass,
  children,
}: {
  label: string
  icon: string
  iconClass: string
  children: ReactNode
}) {
  return (
    <div className="card flex flex-col gap-3 p-5">
      <div className="flex items-start justify-between">
        <span className="text-body-md text-on-surface-variant">{label}</span>
        <span className={`flex h-9 w-9 items-center justify-center rounded-full ${iconClass}`}>
          <Icon name={icon} filled className="text-[20px]" />
        </span>
      </div>
      {children}
    </div>
  )
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-900/20 p-4 backdrop-blur-sm sm:items-center"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-modal aria-label={title} className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-modal">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-headline-md text-ink">{title}</h2>
          <button className="btn-ghost h-8 px-2" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type DragEvent, type FormEvent } from 'react'
import { Avatar, EmptyState, ErrorBanner, Icon, Modal, PageLoader, ProgressBar } from '../components/ui'
import { downloadCsv, initials } from '../lib/format'
import { api } from '../lib/api'
import { relativeTime, shortDate } from '../lib/dates'
import { keys, useJobApplications, useJobFeed } from '../lib/queries'
import { useSession } from '../lib/session'
import type { ApplicationSource, ApplicationStatus, JobApplication } from '../lib/types'

const COLUMNS: { status: ApplicationStatus; label: string; dot: string }[] = [
  { status: 'applied', label: 'Applied', dot: 'bg-outline' },
  { status: 'oa', label: 'Online Assessment', dot: 'bg-tertiary-container' },
  { status: 'interview', label: 'Interview', dot: 'bg-primary-container' },
  { status: 'offer', label: 'Offer', dot: 'bg-secondary' },
  { status: 'rejected', label: 'Rejected', dot: 'bg-outline-variant' },
]

const SOURCES: { value: ApplicationSource; label: string }[] = [
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'referral', label: 'Referral' },
  { value: 'company_site', label: 'Company site' },
  { value: 'other', label: 'Other' },
]
const sourceLabel = (s: ApplicationSource) => SOURCES.find((x) => x.value === s)?.label ?? s

type FormState = Omit<JobApplication, 'id' | 'user_id' | 'created_at' | 'updated_at'>

export default function JobsPage() {
  const { meta } = useSession()
  const jobs = useJobApplications()
  const feed = useJobFeed()
  const qc = useQueryClient()
  const [source, setSource] = useState<ApplicationSource | 'all'>('all')
  const [sort, setSort] = useState<'recent' | 'applied'>('recent')
  const [editing, setEditing] = useState<Partial<JobApplication> | null>(null)
  const [dragOver, setDragOver] = useState<ApplicationStatus | null>(null)

  const refresh = () => qc.invalidateQueries({ queryKey: keys.jobs })

  const move = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ApplicationStatus }) =>
      api<JobApplication>(`/job-applications/${id}`, { method: 'PATCH', json: { status } }),
    onMutate: async ({ id, status }) => {
      await qc.cancelQueries({ queryKey: keys.jobs })
      qc.setQueryData<{ applications: JobApplication[] }>(keys.jobs, (old) =>
        old ? { ...old, applications: old.applications.map((a) => (a.id === id ? { ...a, status } : a)) } : old,
      )
    },
    onSettled: refresh,
  })

  const apps = useMemo(() => {
    const list = (jobs.data?.applications ?? []).filter((a) => source === 'all' || a.source === source)
    return [...list].sort((a, b) =>
      sort === 'recent' ? b.updated_at.localeCompare(a.updated_at) : b.date_applied.localeCompare(a.date_applied),
    )
  }, [jobs.data, source, sort])

  if (jobs.isLoading || !meta) return <PageLoader />
  const stats = jobs.data!.stats
  const all = jobs.data!.applications
  const today = meta.today
  const byStatus = (s: ApplicationStatus) => all.filter((a) => a.status === s).length

  function onDrop(e: DragEvent, status: ApplicationStatus) {
    e.preventDefault()
    setDragOver(null)
    const id = Number(e.dataTransfer.getData('text/plain'))
    const app = all.find((a) => a.id === id)
    if (app && app.status !== status) move.mutate({ id, status })
  }

  function exportCsv() {
    downloadCsv('job-applications.csv', [
      ['company', 'role', 'status', 'source', 'date_applied', 'follow_up_date', 'notes'],
      ...all.map((a) => [a.company, a.role, a.status, a.source, a.date_applied, a.follow_up_date, a.notes]),
    ])
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <span className="pill bg-primary-fixed text-primary-container uppercase">
            <Icon name="lock" className="text-[12px]" /> Private to you
          </span>
          <h1 className="mt-2 text-[28px] leading-tight font-bold tracking-tight text-ink md:text-headline-xl">Job Application Tracker</h1>
          <p className="mt-1 text-body-md text-on-surface-variant">
            Track your job search, upcoming screens, and offers. Drag cards between columns to update their status.
          </p>
        </div>
        <div className="flex gap-3">
          <button className="btn-secondary" onClick={exportCsv} disabled={!all.length}>
            <Icon name="download" className="text-[20px]" /> Export CSV
          </button>
          <button className="btn-primary" onClick={() => setEditing({ status: 'applied' })}>
            <Icon name="add" className="text-[20px]" /> New Application
          </button>
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="card p-6">
          <p className="label">Velocity</p>
          <p className="mt-1 text-headline-md text-ink">Applications this month</p>
          <p className="mt-4">
            <span className="font-mono text-[40px] leading-none font-bold text-ink">{stats.this_month}</span>
            <span className="ml-2 text-body-md text-on-surface-variant">/ {stats.total} all time</span>
          </p>
        </div>
        <div className="card p-6">
          <p className="label">Conversion</p>
          <p className="mt-1 text-headline-md text-ink">Response rate</p>
          <p className="mt-4 flex items-baseline gap-2">
            <span className="font-mono text-[40px] leading-none font-bold text-ink">{Math.round(stats.response_rate * 100)}%</span>
            <span className="text-body-md text-on-surface-variant">({stats.responses} responses)</span>
          </p>
          <div className="mt-3">
            <ProgressBar value={stats.response_rate * 100} className="bg-secondary" />
          </div>
        </div>
        <div className="card p-6">
          <p className="label">Pipeline</p>
          <p className="mt-1 text-headline-md text-ink">Interviews landed</p>
          <p className="mt-4 flex items-baseline gap-2">
            <span className="font-mono text-[40px] leading-none font-bold text-ink">{stats.interviews}</span>
            {stats.offers > 0 && <span className="pill bg-streak-bg font-bold text-streak-text">{stats.offers} offer{stats.offers > 1 ? 's' : ''} in hand</span>}
          </p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            {[
              ['OA', byStatus('oa')],
              ['Interview', byStatus('interview')],
              ['Follow-ups due', stats.follow_ups_due],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-surface-container-low px-2 py-1.5">
                <p className="font-mono font-bold text-ink">{v}</p>
                <p className="font-mono text-label-sm text-on-surface-variant">{k}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          <Chip active={source === 'all'} onClick={() => setSource('all')}>
            All ({all.length})
          </Chip>
          {SOURCES.map((s) => (
            <Chip key={s.value} active={source === s.value} onClick={() => setSource(s.value)}>
              {s.label}
            </Chip>
          ))}
        </div>
        <label className="flex items-center gap-2 font-mono text-label-sm text-on-surface-variant">
          Sort by:
          <select className="rounded-md bg-white px-2 py-1 text-ink shadow-card" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
            <option value="recent">Recent activity</option>
            <option value="applied">Date applied</option>
          </select>
        </label>
      </div>

      <ErrorBanner error={move.error} />

      {all.length === 0 ? (
        <div className="card">
          <EmptyState icon="work" title="No applications logged yet">
            Log each application to see your response rate and interview pipeline.
          </EmptyState>
        </div>
      ) : (
        <div className="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-2 md:mx-0 md:grid md:grid-cols-5 md:overflow-visible md:px-0">
          {COLUMNS.map((col) => {
            const items = apps.filter((a) => a.status === col.status)
            return (
              <section
                key={col.status}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(col.status)
                }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => onDrop(e, col.status)}
                className={`flex w-[280px] shrink-0 snap-start flex-col gap-3 rounded-2xl p-3 transition-colors md:w-auto ${dragOver === col.status ? 'bg-primary-fixed/60 ring-2 ring-primary-container/40' : 'bg-surface-container-low'}`}
              >
                <header className="flex items-center justify-between px-1">
                  <h2 className="flex items-center gap-2 font-semibold text-ink">
                    <span className={`h-2 w-2 rounded-full ${col.dot}`} /> {col.label}
                    <span className="rounded-full bg-slate-100 px-2 font-mono text-label-sm text-slate-600">{items.length}</span>
                  </h2>
                  <button className="rounded p-1 text-on-surface-variant hover:bg-white hover:text-ink" onClick={() => setEditing({ status: col.status })} aria-label={`Add to ${col.label}`}>
                    <Icon name="add" className="text-[20px]" />
                  </button>
                </header>
                {items.map((a) => (
                  <JobCard key={a.id} a={a} today={today} onEdit={() => setEditing(a)} />
                ))}
                {items.length === 0 && <p className="rounded-xl border border-dashed border-outline-variant p-4 text-center text-body-sm text-on-surface-variant">Drop cards here</p>}
              </section>
            )
          })}
        </div>
      )}

      <section className="rounded-2xl bg-streak-bg p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-semibold text-streak-text">
          <Icon name="campaign" className="text-streak" /> Cohort shout-outs this week
        </h2>
        {feed.data?.length ? (
          <ul className="mt-3 flex flex-col gap-2">
            {feed.data.map((f, i) => (
              <li key={i} className="flex items-center gap-3 rounded-xl bg-white/70 px-3 py-2">
                <Avatar name={f.name} id={f.user_id} size={30} />
                <span className="min-w-0 flex-1 text-body-md text-ink">
                  <b>{f.name}</b> {f.status === 'offer' ? 'got an offer 🎉 from' : 'landed an interview with'} <b>{f.company}</b>
                  <span className="text-on-surface-variant"> · {f.role}</span>
                </span>
                <span className="font-mono text-label-sm text-on-surface-variant">{relativeTime(f.at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-body-md text-streak-text/80">
            No shout-outs yet. Mark an application as “share with cohort” and it shows here when you reach the interview or offer stage.
          </p>
        )}
      </section>

      {editing && <JobForm initial={editing} today={today} onClose={() => setEditing(null)} onSaved={refresh} />}
    </div>
  )
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className={`rounded-lg px-3 py-1.5 text-body-md transition-colors ${active ? 'bg-ink text-white' : 'bg-white text-on-surface-variant shadow-card hover:text-ink'}`}>
      {children}
    </button>
  )
}

function JobCard({ a, today, onEdit }: { a: JobApplication; today: string; onEdit: () => void }) {
  const followUp = a.follow_up_date && !['offer', 'rejected'].includes(a.status) ? a.follow_up_date : null
  const overdue = followUp !== null && followUp <= today
  return (
    <article
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', String(a.id))
        e.dataTransfer.effectAllowed = 'move'
      }}
      className="group cursor-grab rounded-[10px] border border-slate-200 bg-white p-3 transition-shadow hover:shadow-lift active:cursor-grabbing"
    >
      <div className="flex items-start gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-container font-mono text-label-sm font-bold text-primary-container">
          {initials(a.company)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink">{a.company}</p>
          <p className="truncate text-body-sm text-on-surface-variant">{sourceLabel(a.source)}</p>
        </div>
        <button className="rounded p-0.5 text-on-surface-variant opacity-60 group-hover:opacity-100 hover:bg-surface-container-low" onClick={onEdit} aria-label={`Edit ${a.company}`}>
          <Icon name="edit" className="text-[18px]" />
        </button>
      </div>
      <p className="mt-2 text-body-md text-ink">{a.role}</p>
      {a.notes && <p className="mt-2 line-clamp-3 rounded-lg bg-surface-container-low p-2 text-body-sm text-on-surface-variant">{a.notes}</p>}
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 font-mono text-label-sm text-on-surface-variant">
        <span className="flex items-center gap-1">
          <Icon name="calendar_today" className="text-[13px]" /> Applied {shortDate(a.date_applied)}
        </span>
        {a.is_public && (
          <span className="flex items-center gap-0.5 text-primary-container" title="Shared with cohort">
            <Icon name="campaign" className="text-[14px]" /> shared
          </span>
        )}
      </div>
      {followUp && (
        <p className={`mt-2 flex items-center gap-1 rounded-md px-2 py-1 font-mono text-label-sm ${overdue ? 'bg-streak-bg text-streak-text' : 'bg-surface-container-low text-on-surface-variant'}`}>
          <Icon name="schedule" className="text-[13px]" /> Follow up {followUp === today ? 'today' : overdue ? `(overdue, ${shortDate(followUp)})` : shortDate(followUp)}
        </p>
      )}
    </article>
  )
}

function JobForm({ initial, today, onClose, onSaved }: { initial: Partial<JobApplication>; today: string; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<FormState>({
    company: initial.company ?? '',
    role: initial.role ?? '',
    date_applied: initial.date_applied ?? today,
    status: initial.status ?? 'applied',
    source: initial.source ?? 'linkedin',
    notes: initial.notes ?? '',
    follow_up_date: initial.follow_up_date ?? null,
    is_public: initial.is_public ?? false,
  })
  const [confirmDelete, setConfirmDelete] = useState(false)
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }))

  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, notes: form.notes?.trim() || null, follow_up_date: form.follow_up_date || null }
      return initial.id
        ? api(`/job-applications/${initial.id}`, { method: 'PATCH', json: body })
        : api('/job-applications', { method: 'POST', json: body })
    },
    onSuccess: () => {
      onSaved()
      onClose()
    },
  })
  const remove = useMutation({
    mutationFn: () => api(`/job-applications/${initial.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      onSaved()
      onClose()
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }

  return (
    <Modal title={initial.id ? 'Edit application' : 'New application'} onClose={onClose}>
      <form className="flex flex-col gap-4" onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="label">Company</span>
            <input className="input" required value={form.company} onChange={(e) => set('company', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="label">Role</span>
            <input className="input" required value={form.role} onChange={(e) => set('role', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="label">Status</span>
            <select className="input" value={form.status} onChange={(e) => set('status', e.target.value as ApplicationStatus)}>
              {COLUMNS.map((c) => (
                <option key={c.status} value={c.status}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="label">Source</span>
            <select className="input" value={form.source} onChange={(e) => set('source', e.target.value as ApplicationSource)}>
              {SOURCES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="label">Date applied</span>
            <input className="input" type="date" required value={form.date_applied} onChange={(e) => set('date_applied', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="label">Follow-up date</span>
            <input className="input" type="date" value={form.follow_up_date ?? ''} onChange={(e) => set('follow_up_date', e.target.value || null)} />
          </label>
        </div>
        <label className="flex flex-col gap-1.5">
          <span className="label">Notes</span>
          <textarea className="input h-24 py-2" value={form.notes ?? ''} onChange={(e) => set('notes', e.target.value)} placeholder="Recruiter name, next steps, prep notes…" />
        </label>
        <label className="flex items-start gap-2 rounded-lg bg-surface-container-low p-3 text-body-md text-on-surface-variant">
          <input type="checkbox" className="mt-0.5 h-[18px] w-[18px] accent-[#22c55e]" checked={form.is_public} onChange={(e) => set('is_public', e.target.checked)} />
          <span>
            <b className="text-ink">Share with cohort</b>: show a shout-out on the group feed when this reaches the interview or offer stage. Company and role
            are shared; notes stay private.
          </span>
        </label>
        <ErrorBanner error={save.error ?? remove.error} />
        <div className="flex items-center justify-between gap-3">
          {initial.id ? (
            confirmDelete ? (
              <span className="flex items-center gap-2">
                <button type="button" className="btn h-9 bg-error text-white hover:bg-on-error-container" onClick={() => remove.mutate()} disabled={remove.isPending}>
                  Delete
                </button>
                <button type="button" className="btn-ghost h-9" onClick={() => setConfirmDelete(false)}>
                  Keep
                </button>
              </span>
            ) : (
              <button type="button" className="btn-ghost h-9 text-error" onClick={() => setConfirmDelete(true)}>
                <Icon name="delete" className="text-[18px]" /> Delete
              </button>
            )
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button className="btn-primary" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  )
}

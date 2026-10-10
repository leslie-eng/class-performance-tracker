import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ExerciseReview } from '../components/admin/ExerciseReview'
import { QuizReview } from '../components/admin/QuizReview'
import { ErrorBanner, Icon } from '../components/ui'
import { api } from '../lib/api'
import { shortDate } from '../lib/dates'
import { useSession } from '../lib/session'
import type { AdminQuiz, Material, QuizKind } from '../lib/types'

type Tab = 'materials' | 'quizzes' | 'exercises'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'materials', label: 'Materials', icon: 'library_books' },
  { id: 'quizzes', label: 'Quizzes', icon: 'quiz' },
  { id: 'exercises', label: 'Coding exercises', icon: 'code' },
]

const materialsKey = ['admin', 'materials'] as const

export default function AdminMaterialsPage() {
  const [tab, setTab] = useState<Tab>('materials')
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-headline-lg text-ink md:text-[28px]">Learning materials</h1>
        <p className="text-body-md text-on-surface-variant">
          Notes, links and documents that quizzes and coding exercises are generated from. Only admins see this page.
        </p>
      </div>
      <div className="flex gap-1 overflow-x-auto rounded-xl bg-surface-container-low p-1" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-body-md ${tab === t.id ? 'bg-white font-semibold text-ink shadow-card' : 'text-on-surface-variant'}`}
          >
            <Icon name={t.icon} className="text-[18px]" /> {t.label}
          </button>
        ))}
      </div>
      {tab === 'materials' && <MaterialsTab />}
      {tab === 'quizzes' && <QuizReview />}
      {tab === 'exercises' && <ExerciseReview />}
    </div>
  )
}

function MaterialsTab() {
  const [filters, setFilters] = useState({ module: '', week_key: '', specialization: '', status: 'active' })
  const [selected, setSelected] = useState<number[]>([])
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString()
  const list = useQuery({ queryKey: [...materialsKey, qs], queryFn: () => api<Material[]>(`/admin/materials?${qs}`) })
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="flex min-w-0 flex-col gap-6">
        <AddMaterial />
        <GenerateFromSelected ids={selected} />
      </div>
      <section className="card min-w-0 p-6">
        <h2 className="flex items-center gap-2 text-headline-md text-ink">
          <Icon name="library_books" className="text-primary-container" /> Materials ({list.data?.length ?? 0})
        </h2>
        <div className="mt-4 grid gap-2 sm:grid-cols-4">
          <input className="input" placeholder="Module" value={filters.module} onChange={(e) => setFilters({ ...filters, module: e.target.value })} />
          <input className="input" type="date" aria-label="Week" value={filters.week_key} onChange={(e) => setFilters({ ...filters, week_key: e.target.value })} />
          <SpecSelect value={filters.specialization} onChange={(v) => setFilters({ ...filters, specialization: v })} placeholder="Any specialization" />
          <select className="input" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
            <option value="">All</option>
          </select>
        </div>
        <ErrorBanner error={list.error} />
        <ul className="mt-4 divide-y divide-slate-100">
          {(list.data ?? []).map((m) => (
            <MaterialRow key={m.id} m={m} checked={selected.includes(m.id)} onCheck={() => toggle(m.id)} />
          ))}
          {list.data && !list.data.length && <li className="py-3 text-body-md text-on-surface-variant">No materials match.</li>}
        </ul>
      </section>
    </div>
  )
}

function SpecSelect({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const { meta } = useSession()
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {(meta?.specializations ?? []).map((s) => (
        <option key={s} value={s}>
          {s.replace(/_/g, ' ')}
        </option>
      ))}
    </select>
  )
}

const KIND_ICON = { text: 'notes', url: 'link', file: 'description' } as const

function MaterialRow({ m, checked, onCheck }: { m: Material; checked: boolean; onCheck: () => void }) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: materialsKey })
  const archive = useMutation({
    mutationFn: () => api(`/admin/materials/${m.id}`, { method: 'PATCH', json: { status: m.status === 'active' ? 'archived' : 'active' } }),
    onSuccess: refresh,
  })
  const refetch = useMutation({ mutationFn: () => api(`/admin/materials/${m.id}/refetch`, { method: 'POST' }), onSuccess: refresh })
  return (
    <li className="flex items-start gap-3 py-3">
      <input type="checkbox" className="mt-1 h-[18px] w-[18px] accent-[#2563eb]" checked={checked} onChange={onCheck} disabled={m.status !== 'active'} aria-label={`Select ${m.title}`} />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 font-medium text-ink">
          <Icon name={KIND_ICON[m.kind]} className="text-[18px] text-on-surface-variant" />
          <span className="truncate">{m.title}</span>
        </p>
        <p className="mt-0.5 text-body-sm text-on-surface-variant">
          {[m.module || 'no module', m.week_key && `week of ${shortDate(m.week_key)}`, m.specialization?.replace(/_/g, ' '), `${m.char_count.toLocaleString()} chars`]
            .filter(Boolean)
            .join(' · ')}
        </p>
        <p className="mt-0.5 text-body-sm">
          {m.digest_ready ? (
            <span className="text-secondary">Digest ready</span>
          ) : m.digest_error ? (
            <span className="text-error">{m.digest_error}</span>
          ) : (
            <span className="text-on-surface-variant">Digest pending…</span>
          )}
        </p>
        <ErrorBanner error={archive.error ?? refetch.error} />
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1 sm:flex-row">
        {m.kind === 'url' && (
          <button className="btn-ghost h-8 px-2" onClick={() => refetch.mutate()} disabled={refetch.isPending} title="Fetch the page again">
            <Icon name="refresh" className="text-[18px]" />
          </button>
        )}
        <button className="btn-ghost h-8 px-2 text-body-sm" onClick={() => archive.mutate()} disabled={archive.isPending}>
          {m.status === 'active' ? 'Archive' : 'Restore'}
        </button>
      </div>
    </li>
  )
}

function AddMaterial() {
  const qc = useQueryClient()
  const [mode, setMode] = useState<'text' | 'url' | 'file'>('text')
  const [f, setF] = useState({ title: '', text: '', url: '', module: '', week_key: '', specialization: '' })
  const [file, setFile] = useState<File | null>(null)
  const set = <K extends keyof typeof f>(k: K, v: string) => setF((s) => ({ ...s, [k]: v }))

  const add = useMutation({
    mutationFn: () => {
      if (mode === 'file') {
        const form = new FormData()
        form.append('file', file!)
        if (f.title.trim()) form.append('title', f.title.trim())
        form.append('module', f.module.trim())
        if (f.week_key) form.append('week_key', f.week_key)
        if (f.specialization) form.append('specialization', f.specialization)
        return api('/admin/materials/upload', { method: 'POST', body: form })
      }
      return api('/admin/materials', {
        method: 'POST',
        json: {
          title: f.title.trim(),
          kind: mode,
          text: mode === 'text' ? f.text : null,
          url: mode === 'url' ? f.url.trim() : null,
          module: f.module.trim(),
          week_key: f.week_key || null,
          specialization: f.specialization || null,
        },
      })
    },
    onSuccess: () => {
      setF((s) => ({ ...s, title: '', text: '', url: '' }))
      setFile(null)
      qc.invalidateQueries({ queryKey: materialsKey })
      setTimeout(() => qc.invalidateQueries({ queryKey: materialsKey }), 8000) // digest arrives in the background
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    add.mutate()
  }

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="add_circle" className="text-primary-container" /> Add material
      </h2>
      <div className="mt-4 flex gap-1 rounded-lg bg-surface-container-low p-1">
        {(['text', 'url', 'file'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`flex-1 rounded-md px-2 py-1.5 text-body-sm ${mode === m ? 'bg-white font-semibold text-ink shadow-card' : 'text-on-surface-variant'}`}
          >
            {m === 'text' ? 'Paste text' : m === 'url' ? 'From URL' : 'Upload file'}
          </button>
        ))}
      </div>
      <form className="mt-4 flex flex-col gap-3" onSubmit={submit}>
        <label className="flex flex-col gap-1.5">
          <span className="label">Title{mode === 'file' && ' (defaults to the file name)'}</span>
          <input className="input" value={f.title} onChange={(e) => set('title', e.target.value)} required={mode !== 'file'} maxLength={200} />
        </label>
        {mode === 'text' && (
          <textarea className="input h-auto min-h-40 py-2 font-mono text-label-md" placeholder="Paste notes or markdown…" value={f.text} onChange={(e) => set('text', e.target.value)} required />
        )}
        {mode === 'url' && <input className="input" type="url" placeholder="https://…" value={f.url} onChange={(e) => set('url', e.target.value)} required />}
        {mode === 'file' && (
          <label className="flex flex-col gap-1.5">
            <span className="label">.md, .txt or .pdf, up to 5 MB</span>
            <input className="text-body-md" type="file" accept=".md,.txt,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          </label>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <input className="input" placeholder="Module" value={f.module} onChange={(e) => set('module', e.target.value)} maxLength={120} />
          <input className="input" type="date" aria-label="Week (drop date)" title="Friday of the drop this belongs to" value={f.week_key} onChange={(e) => set('week_key', e.target.value)} />
          <SpecSelect value={f.specialization} onChange={(v) => set('specialization', v)} placeholder="All specializations" />
        </div>
        <ErrorBanner error={add.error} />
        <button className="btn-primary self-end" disabled={add.isPending || (mode === 'file' && !file)}>
          {add.isPending ? 'Adding…' : 'Add material'}
        </button>
      </form>
    </section>
  )
}

function GenerateFromSelected({ ids }: { ids: number[] }) {
  const qc = useQueryClient()
  const [kind, setKind] = useState<QuizKind>('weekly')
  const [durations, setDurations] = useState<number[]>([10, 20, 30])
  const [weekKey, setWeekKey] = useState('')
  const [spec, setSpec] = useState('')
  const gen = useMutation({
    mutationFn: () =>
      api<(AdminQuiz | { duration_minutes: number; status: string; error: string })[]>('/admin/quizzes/generate', {
        method: 'POST',
        json: { kind, material_ids: ids, durations, week_key: weekKey || null, specialization: kind === 'interview' ? spec || null : null },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'quizzes'] }),
  })
  const toggle = (d: number) => setDurations((s) => (s.includes(d) ? s.filter((x) => x !== d) : [...s, d].sort()))

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="auto_awesome" className="text-primary-container" /> Generate quizzes from selected
      </h2>
      <p className="mt-1 text-body-md text-on-surface-variant">
        {ids.length ? `${ids.length} material${ids.length === 1 ? '' : 's'} selected.` : 'Tick materials in the list first.'} Regenerating replaces a quiz nobody has started yet.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <select className="input" value={kind} onChange={(e) => setKind(e.target.value as QuizKind)}>
          <option value="weekly">Weekly quiz</option>
          <option value="course">Course review (monthly)</option>
          <option value="interview">Interview prep (monthly)</option>
        </select>
        <input className="input" type="date" title={kind === 'weekly' ? 'Drop date (blank = this week)' : 'Any date in the month (blank = this month)'} value={weekKey} onChange={(e) => setWeekKey(e.target.value)} />
        {kind === 'interview' && <SpecSelect value={spec} onChange={setSpec} placeholder="general" />}
      </div>
      <div className="mt-3 flex gap-4">
        {[10, 20, 30].map((d) => (
          <label key={d} className="flex items-center gap-2 text-body-md text-ink">
            <input type="checkbox" className="accent-[#2563eb]" checked={durations.includes(d)} onChange={() => toggle(d)} /> {d} min
          </label>
        ))}
      </div>
      <ErrorBanner error={gen.error} />
      <button className="btn-primary mt-4" disabled={!ids.length || !durations.length || gen.isPending} onClick={() => gen.mutate()}>
        {gen.isPending ? 'Generating… (up to a minute each)' : 'Generate'}
      </button>
      {gen.data && (
        <ul className="mt-3 flex flex-col gap-1 text-body-sm">
          {gen.data.map((r, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span className="text-ink">{r.duration_minutes} min</span>
              <span className={r.status === 'failed' || r.status === 'skipped' ? 'text-error' : 'text-secondary'}>
                {r.status}
                {'error' in r && r.error ? `: ${r.error}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

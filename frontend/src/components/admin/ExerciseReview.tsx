import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../lib/api'
import { useCodeRunner } from '../../lib/runner/useCodeRunner'
import type { AdminExercise, Material } from '../../lib/types'
import { ErrorBanner, Icon, Spinner } from '../ui'

const listKey = ['admin', 'exercises'] as const

/** Admin exercise drafts: generate from materials, edit, verify in the browser, publish. */
export function ExerciseReview() {
  const [open, setOpen] = useState<number | null>(null)
  const list = useQuery({ queryKey: listKey, queryFn: () => api<AdminExercise[]>('/admin/exercises') })
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="flex min-w-0 flex-col gap-6">
        <GenerateExercises onCreated={(id) => setOpen(id)} />
        <section className="card p-6">
          <h2 className="flex items-center gap-2 text-headline-md text-ink">
            <Icon name="code" className="text-primary-container" /> Exercises ({list.data?.length ?? 0})
          </h2>
          <ErrorBanner error={list.error} />
          <ul className="mt-4 divide-y divide-slate-100">
            {(list.data ?? []).map((ex) => (
              <li key={ex.id}>
                <button className={`flex w-full items-start gap-3 py-3 text-left ${open === ex.id ? 'font-semibold' : ''}`} onClick={() => setOpen(ex.id)}>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-ink">{ex.title}</span>
                    <span className="block text-body-sm font-normal text-on-surface-variant">
                      {ex.language} · difficulty {ex.difficulty} · {ex.tests.length} tests ({ex.tests.filter((t) => t.hidden).length} hidden)
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    <span className={`pill ${ex.status === 'published' ? 'bg-secondary-container text-on-secondary-container' : 'bg-primary-fixed text-primary-container'}`}>{ex.status}</span>
                    {!ex.tests_verified && <span className="pill bg-tertiary-fixed text-tertiary">tests unverified</span>}
                  </span>
                </button>
              </li>
            ))}
            {list.data && !list.data.length && <li className="py-3 text-body-md text-on-surface-variant">No exercises yet.</li>}
          </ul>
        </section>
      </div>
      {open ? <ExerciseEditor key={open} id={open} onDeleted={() => setOpen(null)} /> : <p className="text-body-md text-on-surface-variant">Pick an exercise to review it.</p>}
    </div>
  )
}

function GenerateExercises({ onCreated }: { onCreated: (id: number) => void }) {
  const qc = useQueryClient()
  const materials = useQuery({ queryKey: ['admin', 'materials', 'status=active'], queryFn: () => api<Material[]>('/admin/materials?status=active') })
  const [ids, setIds] = useState<number[]>([])
  const [language, setLanguage] = useState<'python' | 'javascript'>('python')
  const [count, setCount] = useState(1)
  const gen = useMutation({
    mutationFn: () => api<{ created: AdminExercise[]; dropped: string[] }>('/admin/exercises/generate', { method: 'POST', json: { material_ids: ids, language, count } }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: listKey })
      if (r.created[0]) onCreated(r.created[0].id)
    },
  })
  const toggle = (id: number) => setIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="auto_awesome" className="text-primary-container" /> Draft exercises from materials
      </h2>
      <ul className="mt-3 flex max-h-48 flex-col gap-1 overflow-y-auto">
        {(materials.data ?? []).map((m) => (
          <li key={m.id}>
            <label className="flex items-center gap-2 text-body-md text-ink">
              <input type="checkbox" className="accent-[#2563eb]" checked={ids.includes(m.id)} onChange={() => toggle(m.id)} />
              <span className="truncate">{m.title}</span>
            </label>
          </li>
        ))}
        {materials.data && !materials.data.length && <li className="text-body-sm text-on-surface-variant">Add materials first.</li>}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <select className="input w-auto" value={language} onChange={(e) => setLanguage(e.target.value as 'python' | 'javascript')}>
          <option value="python">Python</option>
          <option value="javascript">JavaScript</option>
        </select>
        <select className="input w-auto" value={count} onChange={(e) => setCount(Number(e.target.value))}>
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={n}>
              {n} exercise{n > 1 ? 's' : ''}
            </option>
          ))}
        </select>
        <button className="btn-primary" disabled={!ids.length || gen.isPending} onClick={() => gen.mutate()}>
          {gen.isPending ? 'Generating…' : 'Generate drafts'}
        </button>
      </div>
      <ErrorBanner error={gen.error} />
      {gen.data?.dropped.map((d) => (
        <p key={d} className="mt-2 text-body-sm text-error">
          Dropped {d}
        </p>
      ))}
    </section>
  )
}

function ExerciseEditor({ id, onDeleted }: { id: number; onDeleted: () => void }) {
  const qc = useQueryClient()
  const ex = useQuery({ queryKey: ['admin', 'exercise', id], queryFn: () => api<AdminExercise>(`/admin/exercises/${id}`) })
  if (ex.isLoading) return <Spinner />
  if (!ex.data) return <ErrorBanner error={ex.error} />
  return <EditorForm key={ex.data.created_at} ex={ex.data} onSaved={(e) => { qc.setQueryData(['admin', 'exercise', id], e); qc.invalidateQueries({ queryKey: listKey }) }} onDeleted={onDeleted} />
}

function EditorForm({ ex, onSaved, onDeleted }: { ex: AdminExercise; onSaved: (e: AdminExercise) => void; onDeleted: () => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState({
    title: ex.title,
    description_md: ex.description_md,
    starter_code: ex.starter_code,
    reference_solution: ex.reference_solution ?? '',
    entrypoint: ex.entrypoint,
    module: ex.module,
    difficulty: ex.difficulty,
    points: ex.points,
    time_limit_seconds: ex.time_limit_seconds,
    tests: JSON.stringify(ex.tests, null, 2),
  })
  const [verifying, setVerifying] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }))

  const save = useMutation({
    mutationFn: () => {
      let tests
      try {
        tests = JSON.parse(f.tests)
      } catch {
        throw new Error('Tests must be valid JSON: a list of {name, args, expected, hidden}')
      }
      return api<AdminExercise>(`/admin/exercises/${ex.id}`, { method: 'PATCH', json: { ...f, reference_solution: f.reference_solution || null, tests } })
    },
    onSuccess: onSaved,
  })
  const setStatus = useMutation({
    mutationFn: (status: 'draft' | 'published') =>
      status === 'published'
        ? api<AdminExercise>(`/admin/exercises/${ex.id}/publish`, { method: 'POST' })
        : api<AdminExercise>(`/admin/exercises/${ex.id}`, { method: 'PATCH', json: { status } }),
    onSuccess: onSaved,
  })
  const remove = useMutation({
    mutationFn: () => api(`/admin/exercises/${ex.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: listKey })
      onDeleted()
    },
  })
  const area = (k: 'description_md' | 'starter_code' | 'reference_solution' | 'tests', label: string, rows = 6) => (
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      <textarea className="input h-auto py-2 font-mono text-label-md" rows={rows} value={f[k]} onChange={(e) => set(k, e.target.value)} spellCheck={false} />
    </label>
  )

  return (
    <section className="card flex min-w-0 flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-headline-md text-ink">Edit exercise</h2>
        <div className="flex gap-2">
          {ex.status === 'published' ? (
            <button className="btn-secondary" onClick={() => setStatus.mutate('draft')} disabled={setStatus.isPending}>
              Unpublish
            </button>
          ) : (
            <button className="btn-primary" onClick={() => setStatus.mutate('published')} disabled={setStatus.isPending}>
              Publish
            </button>
          )}
        </div>
      </div>
      {!ex.tests_verified && (
        <p className="rounded-lg bg-tertiary-fixed px-3 py-2 text-body-sm text-tertiary">
          Tests unverified: run the reference solution against them before publishing.
        </p>
      )}
      <ErrorBanner error={save.error ?? setStatus.error ?? remove.error} />
      <label className="flex flex-col gap-1.5">
        <span className="label">Title</span>
        <input className="input" value={f.title} onChange={(e) => set('title', e.target.value)} />
      </label>
      <div className="grid gap-3 sm:grid-cols-5">
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="label">Function name</span>
          <input className="input font-mono" value={f.entrypoint} onChange={(e) => set('entrypoint', e.target.value)} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Difficulty</span>
          <input className="input" type="number" min={1} max={5} value={f.difficulty} onChange={(e) => set('difficulty', Number(e.target.value))} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Points</span>
          <input className="input" type="number" min={1} max={100} value={f.points} onChange={(e) => set('points', Number(e.target.value))} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Time limit (s)</span>
          <input className="input" type="number" min={1} max={30} value={f.time_limit_seconds} onChange={(e) => set('time_limit_seconds', Number(e.target.value))} />
        </label>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="label">Module</span>
        <input className="input" value={f.module} onChange={(e) => set('module', e.target.value)} />
      </label>
      {area('description_md', 'Description')}
      {area('starter_code', 'Starter code')}
      {area('reference_solution', 'Reference solution (admins only)')}
      {area('tests', 'Tests (JSON; hidden tests never reach members)', 10)}
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
          Save
        </button>
        <button className="btn-secondary" onClick={() => setVerifying(true)} disabled={!ex.reference_solution}>
          <Icon name="fact_check" className="text-[18px]" /> Verify in browser
        </button>
        {confirmDelete ? (
          <button className="btn-ghost ml-auto text-error" onClick={() => remove.mutate()}>
            Confirm delete
          </button>
        ) : (
          <button className="btn-ghost ml-auto" onClick={() => setConfirmDelete(true)}>
            Delete
          </button>
        )}
      </div>
      {verifying && <BrowserVerifier ex={ex} onDone={onSaved} />}
    </section>
  )
}

/** Runs the saved reference solution against every test in this browser and records the result. */
function BrowserVerifier({ ex, onDone }: { ex: AdminExercise; onDone: (e: AdminExercise) => void }) {
  const runner = useCodeRunner(ex.language)
  const [summary, setSummary] = useState<string | null>(null)
  const verify = useMutation({
    mutationFn: async () => {
      const outcome = await runner.run(ex.reference_solution ?? '', ex.entrypoint, ex.tests, ex.time_limit_seconds)
      const passed = outcome.results.filter((r) => r.passed).length
      const failed = outcome.results.filter((r) => !r.passed).map((r) => `${r.name}: ${r.error ?? `got ${r.actual}`}`)
      setSummary(`${passed}/${ex.tests.length} passed${outcome.error ? ` · ${outcome.error}` : ''}${failed.length ? `\n${failed.join('\n')}` : ''}`)
      return api<AdminExercise>(`/admin/exercises/${ex.id}/verify`, { method: 'POST', json: { passed, total: ex.tests.length } })
    },
    onSuccess: onDone,
  })
  return (
    <div className="rounded-xl bg-surface-container-low p-4">
      <div className="flex items-center gap-3">
        <button className="btn-primary" disabled={runner.status !== 'ready' || verify.isPending} onClick={() => verify.mutate()}>
          Run reference solution
        </button>
        <span className="flex items-center gap-2 text-body-sm text-on-surface-variant">
          {runner.status === 'loading' && (
            <>
              <Spinner /> Loading runner…
            </>
          )}
          {runner.status === 'error' && <span className="text-error">{runner.loadError}</span>}
        </span>
      </div>
      <ErrorBanner error={verify.error} />
      {summary && <pre className="mt-3 font-mono text-label-sm whitespace-pre-wrap text-ink">{summary}</pre>}
    </div>
  )
}

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import CodeEditor from '../components/CodeEditor'
import { ErrorBanner, Icon, PageLoader, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { keys, useCodeAttempt, useExercise } from '../lib/queries'
import { useCodeRunner, type RunOutcome } from '../lib/runner/useCodeRunner'
import type { CodeAttempt, ExerciseDetail } from '../lib/types'

export default function CodeExercisePage() {
  const { id } = useParams()
  const ex = useExercise(Number(id))
  if (ex.isLoading) return <PageLoader />
  if (ex.error || !ex.data) return <ErrorBanner error={ex.error ?? 'Exercise not found'} />
  return <Workspace key={ex.data.id} ex={ex.data} />
}

type SaveState = 'saved' | 'saving' | 'unsaved' | 'error'

function Workspace({ ex }: { ex: ExerciseDetail }) {
  const qc = useQueryClient()
  const [code, setCode] = useState(ex.draft ?? ex.starter_code)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [run, setRun] = useState<(RunOutcome & { code: string }) | null>(null)
  const [attemptId, setAttemptId] = useState<number | undefined>(ex.recent_attempts[0]?.id)
  const [confirmReset, setConfirmReset] = useState(false)
  const lastSaved = useRef(ex.draft ?? ex.starter_code)
  const runner = useCodeRunner(ex.language)
  const attempt = useCodeAttempt(attemptId)

  // Debounced draft autosave.
  useEffect(() => {
    if (code === lastSaved.current) return
    setSaveState('unsaved')
    const t = window.setTimeout(async () => {
      setSaveState('saving')
      try {
        await api(`/coding/exercises/${ex.id}/draft`, { method: 'PUT', json: { code } })
        lastSaved.current = code
        setSaveState('saved')
      } catch {
        setSaveState('error')
      }
    }, 1000)
    return () => window.clearTimeout(t)
  }, [code, ex.id])

  // Warn before leaving with unsaved changes.
  useEffect(() => {
    if (saveState === 'saved') return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [saveState])

  const doRun = async () => {
    const outcome = await runner.run(code, ex.entrypoint, ex.visible_tests, ex.time_limit_seconds)
    setRun({ ...outcome, code })
    return outcome
  }

  const submit = useMutation({
    mutationFn: async () => {
      const outcome = run && run.code === code ? run : await doRun()
      return api<CodeAttempt>(`/coding/exercises/${ex.id}/submit`, {
        method: 'POST',
        json: { code, browser_results: { passed: outcome.results.filter((r) => r.passed).length, total: ex.visible_tests.length } },
      })
    },
    onSuccess: (a) => {
      qc.setQueryData(keys.codeAttempt(a.id), a)
      setAttemptId(a.id)
      qc.invalidateQueries({ queryKey: keys.exercises })
    },
  })

  const busy = runner.status === 'running' || submit.isPending
  const passed = run?.results.filter((r) => r.passed).length ?? 0

  return (
    <div className="flex flex-col gap-4">
      <Link to="/code" className="flex items-center gap-1 text-body-md text-on-surface-variant hover:text-ink">
        <Icon name="arrow_back" className="text-[18px]" /> All exercises
      </Link>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section className="card min-w-0 p-6">
          <h1 className="text-headline-md break-words text-ink">{ex.title}</h1>
          <p className="mt-1 text-body-sm text-on-surface-variant">
            {[ex.language, ex.module, `difficulty ${ex.difficulty}`, `${ex.points} pts`].filter(Boolean).join(' · ')}
          </p>
          <div className="mt-4 text-body-md break-words whitespace-pre-wrap text-ink">{ex.description_md}</div>
          <p className="label mt-6">Visible tests</p>
          <ul className="mt-2 flex flex-col gap-1.5 font-mono text-label-sm">
            {ex.visible_tests.map((t) => (
              <li key={t.name} className="rounded-lg bg-surface-container-low px-3 py-2 break-all text-ink">
                {ex.entrypoint}({t.args.map((a) => JSON.stringify(a)).join(', ')}) → {JSON.stringify(t.expected)}
              </li>
            ))}
          </ul>
          {ex.hidden_test_count > 0 && (
            <p className="mt-2 text-body-sm text-on-surface-variant">Plus {ex.hidden_test_count} hidden test{ex.hidden_test_count === 1 ? '' : 's'}, checked only in verified runs.</p>
          )}
          <p className="mt-4 rounded-lg bg-primary-fixed/40 p-3 text-body-sm text-ink">
            {ex.runner === 'remote'
              ? `Submissions are verified on the server against every test. A full pass earns ${ex.points} pts.`
              : `Runs happen in your browser on the visible tests, so they count as practice: a full pass earns ${ex.unverified_points} of ${ex.points} pts.`}
          </p>
        </section>

        <section className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-body-sm text-on-surface-variant">
              {runner.status === 'loading' && (
                <>
                  <Spinner /> Loading {ex.language === 'python' ? 'Python' : 'the runner'}…
                </>
              )}
              {runner.status === 'error' && <span className="text-error">{runner.loadError}</span>}
              {runner.status === 'ready' && 'Ready'}
              {runner.status === 'running' && (
                <>
                  <Spinner /> Running…
                </>
              )}
            </span>
            <span className="text-body-sm text-on-surface-variant">
              {{ saved: 'Draft saved', saving: 'Saving…', unsaved: 'Unsaved changes', error: 'Draft not saved' }[saveState]}
            </span>
          </div>
          <CodeEditor value={code} onChange={setCode} language={ex.language} label={`${ex.title} solution`} />
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" disabled={busy || runner.status === 'loading'} onClick={doRun}>
              <Icon name="play_arrow" className="text-[18px]" /> Run
            </button>
            <button className="btn-primary" disabled={busy || runner.status === 'loading'} onClick={() => submit.mutate()}>
              <Icon name="send" className="text-[18px]" /> {submit.isPending ? 'Submitting…' : 'Submit'}
            </button>
            {confirmReset ? (
              <span className="flex gap-2">
                <button className="btn-ghost text-error" onClick={() => { setCode(ex.starter_code); setConfirmReset(false) }}>
                  Discard my code
                </button>
                <button className="btn-ghost" onClick={() => setConfirmReset(false)}>
                  Keep it
                </button>
              </span>
            ) : (
              <button className="btn-ghost ml-auto" onClick={() => setConfirmReset(true)}>
                Reset to starter
              </button>
            )}
          </div>
          <ErrorBanner error={submit.error} />

          {run && (
            <div className="card p-4">
              <p className="label">
                Practice run · {passed}/{run.results.length} visible tests passed
              </p>
              {run.error && <pre className="mt-2 rounded-lg bg-error-container p-3 font-mono text-label-sm whitespace-pre-wrap text-on-error-container">{run.error}</pre>}
              <ul className="mt-2 flex flex-col gap-1.5">
                {run.results.map((r) => (
                  <li key={r.name} className="flex items-start gap-2 text-body-sm">
                    <Icon name={r.passed ? 'check_circle' : 'cancel'} className={`text-[18px] ${r.passed ? 'text-secondary' : 'text-error'}`} />
                    <span className="min-w-0 break-words">
                      <span className="font-medium text-ink">{r.name}</span>
                      {!r.passed && (
                        <span className="block font-mono text-label-sm text-on-surface-variant">
                          {r.error ?? `expected ${JSON.stringify(ex.visible_tests.find((t) => t.name === r.name)?.expected)}, got ${r.actual}`}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
              {run.output && (
                <>
                  <p className="label mt-3">Console</p>
                  <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-inverse-surface p-3 font-mono text-label-sm whitespace-pre-wrap text-white">{run.output}</pre>
                </>
              )}
            </div>
          )}

          {attempt.data && <AttemptCard a={attempt.data} />}
        </section>
      </div>
    </div>
  )
}

function AttemptCard({ a }: { a: CodeAttempt }) {
  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="label">
          Last submission · {a.passed_count}/{a.total_count} {a.verified ? 'tests (verified)' : 'visible tests (practice)'}
        </p>
        <span className="pill bg-secondary-container text-on-secondary-container">+{a.points_awarded} pts</span>
      </div>
      {a.runner_error && <p className="mt-2 text-body-sm text-on-surface-variant">{a.runner_error}</p>}
      {a.results && (
        <ul className="mt-2 flex flex-col gap-1 text-body-sm">
          {a.results.map((r) => (
            <li key={r.name} className={r.passed ? 'text-secondary' : 'text-error'}>
              {r.passed ? '✓' : '✗'} {r.name}
              {r.actual && !r.passed ? ` (${r.actual})` : ''}
            </li>
          ))}
        </ul>
      )}
      <p className="label mt-3">AI feedback</p>
      {a.grading_status === 'pending' ? (
        <p className="mt-1 flex items-center gap-2 text-body-md text-on-surface-variant">
          <Spinner /> Reviewing your code…
        </p>
      ) : (
        <p className={`mt-1 text-body-md ${a.grading_status === 'failed' ? 'text-on-surface-variant' : 'text-ink'}`}>{a.ai_feedback}</p>
      )}
    </div>
  )
}

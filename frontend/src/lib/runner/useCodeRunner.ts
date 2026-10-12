import { useCallback, useEffect, useRef, useState } from 'react'
import type { Language, RunRequest, TestCase, TestRun, WorkerMessage } from './protocol'

export type RunnerStatus = 'loading' | 'ready' | 'running' | 'error'

export interface RunOutcome {
  results: TestRun[]
  output: string
  error?: string
  timedOut?: boolean
}

function spawn(language: Language): Worker {
  return language === 'python'
    ? new Worker(new URL('./pyodide.worker.ts', import.meta.url), { type: 'module' })
    : new Worker(new URL('./js.worker.ts', import.meta.url), { type: 'module' })
}

/**
 * A code-runner worker for the editor page. It's created when the page mounts (so Pyodide
 * only downloads there) and terminated after `timeLimit` seconds of running, which is the
 * only reliable way to stop an infinite loop. A fresh worker is started for the next run.
 */
export function useCodeRunner(language: Language) {
  const [status, setStatus] = useState<RunnerStatus>('loading')
  const [loadError, setLoadError] = useState<string | null>(null)
  const worker = useRef<Worker | null>(null)
  const nextId = useRef(1)

  const start = useCallback(() => {
    const w = spawn(language)
    w.addEventListener('message', (e: MessageEvent<WorkerMessage>) => {
      if (e.data.type === 'status') {
        setStatus(e.data.status)
        setLoadError(e.data.error ?? null)
      }
    })
    w.addEventListener('error', (e) => {
      setStatus('error')
      setLoadError(e.message || 'The code runner crashed')
    })
    worker.current = w
    return w
  }, [language])

  useEffect(() => {
    start()
    return () => {
      worker.current?.terminate()
      worker.current = null
    }
  }, [start])

  const run = useCallback(
    (code: string, entrypoint: string, tests: TestCase[], timeLimit: number) =>
      new Promise<RunOutcome>((resolve) => {
        const w = worker.current ?? start()
        const id = nextId.current++
        let timer: number | undefined
        setStatus('running')
        const onMessage = (e: MessageEvent<WorkerMessage>) => {
          const msg = e.data
          if (msg.type === 'started' && msg.id === id) {
            // Count only execution time, not the Pyodide download.
            timer = window.setTimeout(() => {
              w.removeEventListener('message', onMessage)
              w.terminate()
              worker.current = null
              start() // fresh worker for the next run
              resolve({
                results: tests.map((t) => ({ name: t.name, passed: false, error: 'Not run: time limit hit' })),
                output: '',
                error: `Stopped after ${timeLimit}s. Check for an infinite loop.`,
                timedOut: true,
              })
            }, timeLimit * 1000)
          } else if (msg.type === 'result' && msg.id === id) {
            window.clearTimeout(timer)
            w.removeEventListener('message', onMessage)
            setStatus('ready')
            resolve({ results: msg.results, output: msg.output, error: msg.error })
          }
        }
        w.addEventListener('message', onMessage)
        const req: RunRequest = { type: 'run', id, code, entrypoint, tests }
        w.postMessage(req)
      }),
    [start],
  )

  return { status, loadError, run }
}

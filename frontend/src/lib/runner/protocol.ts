// Messages between the editor page and the code-runner workers. Workers only ever get
// the member's code and the visible tests: never the auth token or the API URL.

export type Language = 'python' | 'javascript'

export interface TestCase {
  name: string
  args: unknown[]
  expected: unknown
}

export interface TestRun {
  name: string
  passed: boolean
  actual?: string
  error?: string
}

export interface RunRequest {
  type: 'run'
  id: number
  code: string
  entrypoint: string
  tests: TestCase[]
}

export type WorkerMessage =
  | { type: 'status'; status: 'loading' | 'ready' | 'error'; error?: string }
  | { type: 'started'; id: number }
  | { type: 'result'; id: number; results: TestRun[]; output: string; error?: string }

export const OUTPUT_LIMIT = 64 * 1024

/** The worker global, typed without pulling the WebWorker lib into the whole app. */
export interface WorkerScope {
  postMessage(message: WorkerMessage): void
  onmessage: ((e: MessageEvent<RunRequest>) => void) | null
}

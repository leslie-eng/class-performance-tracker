// Runs JavaScript in a dedicated worker, in the member's browser, with network APIs removed.
import { OUTPUT_LIMIT, type RunRequest, type TestRun, type WorkerScope } from './protocol'

const scope = self as unknown as WorkerScope
const globals = self as unknown as Record<string, unknown>

// The worker has no token to leak, but there's no reason for exercise code to reach the network.
for (const name of ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'importScripts', 'indexedDB', 'caches']) {
  try {
    Object.defineProperty(globals, name, { value: undefined, configurable: false, writable: false })
  } catch {
    /* not defined in this browser */
  }
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
const show = (v: unknown) => {
  try {
    return typeof v === 'string' ? v : JSON.stringify(v)
  } catch {
    return String(v)
  }
}

scope.onmessage = (e: MessageEvent<RunRequest>) => {
  const { id, code, entrypoint, tests } = e.data
  let output = ''
  const log = (...args: unknown[]) => {
    if (output.length < OUTPUT_LIMIT) output += args.map(show).join(' ') + '\n'
  }
  const sandboxConsole = { log, info: log, warn: log, error: log, debug: log }
  scope.postMessage({ type: 'started', id })
  let fn: unknown
  try {
    // entrypoint is validated server-side as a plain identifier.
    fn = new Function('console', `"use strict";\n${code}\n;return typeof ${entrypoint} === 'function' ? ${entrypoint} : undefined;`)(sandboxConsole)
  } catch (err) {
    scope.postMessage({ type: 'result', id, results: [], output, error: String(err) })
    return
  }
  if (typeof fn !== 'function') {
    scope.postMessage({ type: 'result', id, results: [], output, error: `Define a function called ${entrypoint}` })
    return
  }
  const results: TestRun[] = tests.map((t) => {
    try {
      const got = (fn as (...a: unknown[]) => unknown)(...structuredClone(t.args))
      const norm = JSON.parse(JSON.stringify(got ?? null))
      return { name: t.name, passed: same(norm, t.expected), actual: String(JSON.stringify(got)).slice(0, 300) }
    } catch (err) {
      return { name: t.name, passed: false, error: String(err).slice(0, 300) }
    }
  })
  scope.postMessage({ type: 'result', id, results, output: output.slice(0, OUTPUT_LIMIT) })
}

scope.postMessage({ type: 'status', status: 'ready' })

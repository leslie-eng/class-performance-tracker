// Runs Python with Pyodide, in the member's browser. Loaded only when an editor page opens.
import { OUTPUT_LIMIT, type WorkerScope } from './protocol'

const PYODIDE_VERSION = '314.0.7' // pinned; bump deliberately
const INDEX_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`

interface Pyodide {
  runPythonAsync(code: string): Promise<unknown>
  setStdout(opts: { batched: (s: string) => void }): void
  setStderr(opts: { batched: (s: string) => void }): void
  globals: { set(name: string, value: unknown): void }
}

const scope = self as unknown as WorkerScope

// Runs the member's code in a fresh namespace, then each test, comparing JSON-normalised
// results (so tuples equal lists, as in the server's sandbox harness).
const HARNESS = `
import json, traceback
def __ct_run(code, entry, tests_json):
    ns = {"__name__": "__main__"}
    try:
        exec(compile(code, "solution.py", "exec"), ns)
    except BaseException:
        return json.dumps({"error": traceback.format_exc(limit=2), "results": []})
    fn = ns.get(entry)
    if not callable(fn):
        return json.dumps({"error": f"Define a function called {entry}", "results": []})
    out = []
    for t in json.loads(tests_json):
        try:
            got = fn(*t["args"])
            norm = json.loads(json.dumps(got, default=repr))
            out.append({"name": t["name"], "passed": norm == t["expected"], "actual": json.dumps(got, default=repr)[:300]})
        except BaseException as e:
            out.append({"name": t["name"], "passed": False, "error": (type(e).__name__ + ": " + str(e))[:300]})
    return json.dumps({"results": out})
__ct_run(__ct_code, __ct_entry, __ct_tests)
`

let pyodide: Promise<Pyodide> | null = null

function load(): Promise<Pyodide> {
  if (!pyodide) {
    scope.postMessage({ type: 'status', status: 'loading' })
    pyodide = import(/* @vite-ignore */ `${INDEX_URL}pyodide.mjs`)
      .then((m: { loadPyodide: (o: { indexURL: string }) => Promise<Pyodide> }) => m.loadPyodide({ indexURL: INDEX_URL }))
      .then((py) => {
        scope.postMessage({ type: 'status', status: 'ready' })
        return py
      })
      .catch((err) => {
        scope.postMessage({ type: 'status', status: 'error', error: `Couldn't load Python (${String(err)})` })
        pyodide = null
        throw err
      })
  }
  return pyodide
}

load().catch(() => {})

scope.onmessage = async (e) => {
  const { id, code, entrypoint, tests } = e.data
  let output = ''
  const capture = (s: string) => {
    if (output.length < OUTPUT_LIMIT) output += s + '\n'
  }
  let py: Pyodide
  try {
    py = await load()
  } catch (err) {
    scope.postMessage({ type: 'result', id, results: [], output: '', error: String(err) })
    return
  }
  py.setStdout({ batched: capture })
  py.setStderr({ batched: capture })
  py.globals.set('__ct_code', code)
  py.globals.set('__ct_entry', entrypoint)
  py.globals.set('__ct_tests', JSON.stringify(tests))
  scope.postMessage({ type: 'started', id })
  try {
    const parsed = JSON.parse(String(await py.runPythonAsync(HARNESS)))
    scope.postMessage({ type: 'result', id, results: parsed.results ?? [], error: parsed.error, output: output.slice(0, OUTPUT_LIMIT) })
  } catch (err) {
    scope.postMessage({ type: 'result', id, results: [], output: output.slice(0, OUTPUT_LIMIT), error: String(err) })
  }
}

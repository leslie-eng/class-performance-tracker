import CodeMirror from '@uiw/react-codemirror'
import { useEffect, useSyncExternalStore } from 'react'
import { Spinner } from './ui'

// Type-only, so `verbatimModuleSyntax` erases it and nothing new enters the bundle.
// `Extension` is defined in @codemirror/state (a dependency of every language pack).
import type { Extension } from '@codemirror/state'

/**
 * Language packs are loaded on demand *per language*, rather than both being imported at the
 * top of this file. Importing both there pulled python + javascript (and their whole
 * grammar/Lezer dependency trees) into the CodeExercise chunk even when a member only ever
 * opened a Python exercise. A dynamic import lets Vite split each language into its own chunk.
 */
const languageLoaders: Record<'python' | 'javascript', () => Promise<Extension>> = {
  python: () => import('@codemirror/lang-python').then((m) => m.python()),
  javascript: () => import('@codemirror/lang-javascript').then((m) => m.javascript()),
}

/**
 * Module-level cache + tiny store, read with useSyncExternalStore so render stays pure.
 * Doing this with useState + setState inside an effect tripped oxlint's set-state-in-effect
 * rule (a cascading render on mount).
 */
const cache = new Map<string, Extension>()
const inFlight = new Map<string, Promise<Extension>>()
const listeners = new Set<() => void>()
let version = 0

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange)
  return () => {
    listeners.delete(onChange)
  }
}

const getVersion = () => version

/** Starts the import for `language` once. Resolving bumps the version, which re-renders subscribers. */
function ensureLoaded(language: 'python' | 'javascript') {
  if (cache.has(language) || inFlight.has(language)) return
  const promise = languageLoaders[language]()
    .then((ext) => {
      cache.set(language, ext)
      return ext
    })
    .finally(() => {
      inFlight.delete(language)
    })
  inFlight.set(language, promise)
  promise.then(() => {
    version += 1
    for (const listener of listeners) listener()
  })
}

/** CodeMirror 6 editor (light on phones, unlike Monaco). Scrolls horizontally inside itself, never the page. */
export default function CodeEditor({
  value,
  onChange,
  language,
  minHeight = '320px',
  label,
}: {
  value: string
  onChange: (v: string) => void
  language: 'python' | 'javascript'
  minHeight?: string
  label: string
}) {
  // Re-render when a language pack finishes loading. The effect only kicks off the import;
  // it never calls setState, so there is no cascading render.
  useSyncExternalStore(subscribe, getVersion, getVersion)
  useEffect(() => {
    ensureLoaded(language)
  }, [language])

  const extension = cache.get(language)

  // minHeight lives on the wrapper in both states, so the editor doesn't jump once it loads.
  return (
    <div
      className="max-w-full min-w-0 overflow-hidden rounded-xl border border-slate-200 font-mono text-[14px]"
      style={{ minHeight }}
    >
      {extension ? (
        <CodeMirror
          value={value}
          onChange={onChange}
          extensions={[extension]}
          minHeight={minHeight}
          aria-label={label}
          basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true, autocompletion: false }}
        />
      ) : (
        <div className="flex items-center justify-center text-on-surface-variant" style={{ minHeight }}>
          <Spinner className="text-[24px]" />
        </div>
      )}
    </div>
  )
}

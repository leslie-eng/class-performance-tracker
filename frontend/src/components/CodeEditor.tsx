import { javascript } from '@codemirror/lang-javascript'
import { python } from '@codemirror/lang-python'
import CodeMirror from '@uiw/react-codemirror'
import { useMemo } from 'react'

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
  const extensions = useMemo(() => [language === 'python' ? python() : javascript()], [language])
  return (
    <div className="max-w-full min-w-0 overflow-hidden rounded-xl border border-slate-200 font-mono text-[14px]">
      <CodeMirror
        value={value}
        onChange={onChange}
        extensions={extensions}
        minHeight={minHeight}
        aria-label={label}
        basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true, autocompletion: false }}
      />
    </div>
  )
}

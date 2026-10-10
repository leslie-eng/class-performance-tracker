import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorBanner, Icon, PageLoader } from '../components/ui'
import { useExercises } from '../lib/queries'

function Difficulty({ level }: { level: number }) {
  return (
    <span className="flex gap-0.5" aria-label={`Difficulty ${level} of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={`h-1.5 w-3 rounded-full ${n <= level ? 'bg-primary-container' : 'bg-surface-container-high'}`} />
      ))}
    </span>
  )
}

export default function CodePage() {
  const list = useExercises()
  const [module, setModule] = useState('')
  const [difficulty, setDifficulty] = useState(0)
  if (list.isLoading) return <PageLoader />
  if (list.error) return <ErrorBanner error={list.error} />
  const all = list.data ?? []
  const modules = [...new Set(all.map((e) => e.module).filter(Boolean))].sort()
  const shown = all.filter((e) => (!module || e.module === module) && (!difficulty || e.difficulty === difficulty))

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-headline-lg text-ink md:text-[28px]">Coding exercises</h1>
        <p className="text-body-md text-on-surface-variant">
          Coursework you can run right here in the browser. Points are separate from the challenge leaderboard and streaks.
        </p>
      </div>
      {all.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <select className="input w-auto" value={module} onChange={(e) => setModule(e.target.value)} aria-label="Module">
            <option value="">All modules</option>
            {modules.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
          <select className="input w-auto" value={difficulty} onChange={(e) => setDifficulty(Number(e.target.value))} aria-label="Difficulty">
            <option value={0}>Any difficulty</option>
            {[1, 2, 3, 4, 5].map((d) => (
              <option key={d} value={d}>
                Difficulty {d}
              </option>
            ))}
          </select>
        </div>
      )}
      {shown.length ? (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((e) => (
            <li key={e.id}>
              <Link to={`/code/${e.id}`} className="card flex h-full flex-col gap-3 p-5 transition-shadow hover:shadow-lift">
                <div className="flex items-start justify-between gap-3">
                  <p className="font-semibold break-words text-ink">{e.title}</p>
                  {e.solved && (
                    <span className={`pill shrink-0 ${e.verified ? 'bg-secondary-container text-on-secondary-container' : 'bg-primary-fixed text-primary-container'}`}>
                      <Icon name="check" className="text-[14px]" /> {e.verified ? 'Solved' : 'Solved (practice)'}
                    </span>
                  )}
                </div>
                <div className="mt-auto flex flex-wrap items-center gap-3 text-body-sm text-on-surface-variant">
                  <span className="font-mono">{e.language}</span>
                  {e.module && <span>{e.module}</span>}
                  <Difficulty level={e.difficulty} />
                  <span className="ml-auto font-mono">
                    {e.points_earned}/{e.points} pts
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="card">
          <EmptyState icon="code_off" title={all.length ? 'Nothing matches those filters' : 'No exercises yet'}>
            {all.length ? 'Try another module or difficulty.' : 'Your admins publish coursework exercises here.'}
          </EmptyState>
        </div>
      )}
    </div>
  )
}

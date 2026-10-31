import { useMeta } from '../lib/queries'
import { Icon } from './ui'

/** "AI · GPT-6 Luna": which model produced an AI output. Renders nothing for older outputs without one. */
export function AiModelBadge({ model, className = '' }: { model?: string | null; className?: string }) {
  const meta = useMeta()
  if (!model) return null
  const label = meta.data?.ai_model_labels?.[model] ?? model.split('/').pop()
  return (
    <span
      title={model}
      className={`inline-flex items-center gap-1 rounded-full bg-surface-container-low px-2 py-0.5 text-label-sm text-on-surface-variant ${className}`}
    >
      <Icon name="smart_toy" className="text-[14px]" />
      AI · {label}
    </span>
  )
}

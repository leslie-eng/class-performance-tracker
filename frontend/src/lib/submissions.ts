import type { Submission } from './types'

/** A short human title for a submission. */
export function submissionTitle(s: Submission): string {
  if (s.submission_type === 'article') {
    if (s.ai_details?.title) return s.ai_details.title
    try {
      const url = new URL(s.content)
      const slug = url.pathname.split('/').filter(Boolean).pop()
      return slug ? decodeURIComponent(slug).replace(/[-_]+/g, ' ').replace(/\s[0-9a-f]{6,}$/i, '') : url.hostname
    } catch {
      return s.content
    }
  }
  const firstLine = s.content
    .split('\n')
    .map((l) => l.trim())
    .find((l) => l && !/^(import|from|#include|using|package)\b/.test(l))
  return firstLine ? firstLine.replace(/^(#|\/\/|--)\s*/, '').slice(0, 80) : `${s.language ?? 'Code'} solution`
}

export function articleHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export const LANGUAGES = ['python', 'sql', 'javascript', 'typescript', 'java', 'go', 'rust', 'c', 'cpp', 'csharp', 'bash', 'other']

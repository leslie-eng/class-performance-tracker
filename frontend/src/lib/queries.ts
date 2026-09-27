import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import type {
  Challenge,
  Dashboard,
  FeedItem,
  JobApplication,
  JobStats,
  LeaderboardRow,
  Meta,
  Submission,
  User,
} from './types'

export const keys = {
  me: ['me'] as const,
  meta: ['meta'] as const,
  challenges: ['challenges'] as const,
  myChallenges: ['challenges', 'mine'] as const,
  submissions: (challengeId?: number) => ['submissions', challengeId ?? 'all'] as const,
  submission: (id: number) => ['submission', id] as const,
  leaderboard: (challengeId: number | 'global') => ['leaderboard', challengeId] as const,
  dashboard: (userId: number, challengeId?: number) => ['dashboard', userId, challengeId ?? 'all'] as const,
  jobs: ['jobs'] as const,
  feed: ['jobs', 'feed'] as const,
}

export const useMe = (enabled = true) =>
  useQuery({ queryKey: keys.me, queryFn: () => api<User>('/auth/me'), enabled, retry: false })

export const useMeta = () =>
  useQuery({ queryKey: keys.meta, queryFn: () => api<Meta>('/meta'), staleTime: 5 * 60_000 })

export const useChallenges = () =>
  useQuery({ queryKey: keys.challenges, queryFn: () => api<Challenge[]>('/challenges') })

export const useMyChallenges = (enabled = true) =>
  useQuery({ queryKey: keys.myChallenges, queryFn: () => api<Challenge[]>('/challenges/mine'), enabled })

export const useMySubmissions = (challengeId?: number) =>
  useQuery({
    queryKey: keys.submissions(challengeId),
    queryFn: () => api<Submission[]>(`/submissions/me?limit=500${challengeId ? `&challenge_id=${challengeId}` : ''}`),
  })

/** Polls while grading is pending. */
export const useSubmission = (id: number | undefined) =>
  useQuery({
    queryKey: keys.submission(id ?? 0),
    queryFn: () => api<Submission>(`/submissions/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.grading_status === 'pending' ? 3000 : false),
  })

export const useLeaderboard = (challengeId: number | 'global' | undefined) =>
  useQuery({
    queryKey: keys.leaderboard(challengeId ?? 'global'),
    queryFn: () => api<LeaderboardRow[]>(`/leaderboard/${challengeId}`),
    enabled: challengeId !== undefined,
    refetchInterval: 60_000,
  })

export const useDashboard = (userId: number | undefined, challengeId?: number) =>
  useQuery({
    queryKey: keys.dashboard(userId ?? 0, challengeId),
    queryFn: () => api<Dashboard>(`/members/${userId}/dashboard${challengeId ? `?challenge_id=${challengeId}` : ''}`),
    enabled: !!userId,
  })

export const useJobApplications = () =>
  useQuery({
    queryKey: keys.jobs,
    queryFn: () => api<{ applications: JobApplication[]; stats: JobStats }>('/job-applications/me'),
  })

export const useJobFeed = () =>
  useQuery({ queryKey: keys.feed, queryFn: () => api<FeedItem[]>('/job-applications/feed') })

/** Invalidate everything that depends on submissions/points. */
export function useInvalidateProgress() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['submissions', 'submission', 'leaderboard', 'dashboard'].map((k) => qc.invalidateQueries({ queryKey: [k] })),
    )
}

export function useEnroll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (challengeId: number) => api(`/challenges/${challengeId}/enroll`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.challenges }),
  })
}

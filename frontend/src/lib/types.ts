// Mirrors backend/app/schemas.py

export type TaskTypes = 'code' | 'article' | 'both'
export type SubmissionType = 'code' | 'article'
export type GradingStatus = 'not_applicable' | 'pending' | 'done' | 'failed'
export type ApplicationStatus = 'applied' | 'oa' | 'interview' | 'offer' | 'rejected'
export type ApplicationSource = 'linkedin' | 'referral' | 'company_site' | 'other'

export interface User {
  id: number
  name: string
  email: string
  phone_number: string | null
  is_admin: boolean
  whatsapp_opt_in: boolean
  joined_at: string
}

export interface ScoringRules {
  code_points: number
  article_points: number
  article_ai_bonus_max: number
  streak_bonus_points: number
  streak_bonus_every: number
  missed_day_penalty: number
  backfill_days: number
  lag_threshold: number
  ai_code_review: boolean
  lag_message?: string
}

export interface Challenge {
  id: number
  name: string
  description: string | null
  start_date: string
  end_date: string
  total_days: number
  task_types_allowed: TaskTypes
  scoring_rules: Partial<ScoringRules>
  effective_rules: ScoringRules
}

export interface Enrollment {
  id: number
  user_id: number
  challenge_id: number
  joined_at: string
}

export interface RubricBreakdown {
  clarity: number
  technical_accuracy: number
  depth: number
  originality: number
}

export interface Submission {
  id: number
  enrollment_id: number
  day_number: number
  submission_type: SubmissionType
  content: string
  language: string | null
  problem_link: string | null
  counts_for_streak: boolean
  grading_status: GradingStatus
  ai_score: number | null
  ai_breakdown: RubricBreakdown | null
  ai_feedback: string | null
  ai_details: { title?: string; strengths?: string[]; improvements?: string[] } | null
  grade_overridden: boolean
  points_awarded: number
  submitted_at: string
}

export interface LeaderboardRow {
  rank: number
  user_id: number
  name: string
  total_points: number
  current_streak: number
  longest_streak: number
  days_completed: number
  avg_ai_score: number | null
}

export interface ChallengeProgress {
  challenge_id: number
  challenge: string
  current_streak: number
  longest_streak: number
  days_completed: number
  total_days: number
  total_points: number
  rank: number | null
}

export interface JobStats {
  total: number
  this_month: number
  responses: number
  response_rate: number
  interviews: number
  offers: number
  follow_ups_due: number
}

export interface Dashboard {
  user: User
  month: string
  heatmap: Record<string, number>
  challenges: ChallengeProgress[]
  total_points: number
  global_rank: number | null
  recent_submissions: Submission[]
  job_stats: JobStats | null
}

export interface JobApplication {
  id: number
  user_id: number
  company: string
  role: string
  date_applied: string
  status: ApplicationStatus
  source: ApplicationSource
  notes: string | null
  follow_up_date: string | null
  is_public: boolean
  created_at: string
  updated_at: string
}

export interface FeedItem {
  user_id: number
  name: string
  company: string
  role: string
  status: ApplicationStatus
  at: string
}

export interface Meta {
  timezone: string
  today: string
}

export interface LaggingMember {
  user_id: number
  name: string
  challenge_id: number
  challenge: string
  days_missed: number
  streak_lost: number
  points: number
  notified: boolean
  skipped_reason: string | null
}

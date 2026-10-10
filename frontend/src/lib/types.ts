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
  specialization: string | null
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
  specializations: string[]
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

// --- Friday Drop and quizzes (backend/app/schemas_weekly.py) ---

export type QuizKind = 'weekly' | 'interview' | 'course'

export interface Concept {
  title: string
  one_liner: string
}

export interface Brief {
  id: number
  week_key: string
  status: 'draft' | 'ready' | 'sent'
  summary: string | null
  concepts: Concept[]
  summary_error: string | null
  has_notes: boolean
  updated_at: string
  source_notes?: string | null
}

export interface Proposal {
  id: number
  week_key: string
  slot: number
  title: string
  description: string
  proposer_id: number
  proposer_name: string
  picks: number
  picked_by_me: boolean
}

export interface QuizSlot {
  kind: QuizKind
  period_key: string
  specialization: string | null
  duration_minutes: number
  question_count: number
  available: boolean
  reason: string | null
  attempt_id: number | null
  submitted: boolean
  score: number | null
  max_score: number | null
}

export interface WeeklyCurrent {
  week_key: string
  month_key: string
  server_now: string
  ai_configured: boolean
  brief: Brief | null
  projects: Proposal[]
  my_pick: number | null
  upcoming: { week_key: string; projects: Proposal[]; slots_left: number; my_proposal_id: number | null; has_notes: boolean }
  quizzes: QuizSlot[]
}

export interface QuizQuestion {
  id: string
  type: 'mcq' | 'short'
  difficulty: number
  prompt: string
  options: string[] | null
  points: number
}

export interface QuizResult extends QuizQuestion {
  your_answer: number | string | null
  correct_answer: number | string
  explanation: string
  earned: number
  feedback: string | null
}

export type QuizAnswers = Record<string, number | string>

export interface QuizAttempt {
  id: number
  quiz_id: number
  kind: QuizKind
  specialization: string | null
  duration_minutes: number
  started_at: string
  deadline_at: string
  ends_at: string
  server_now: string
  submitted: boolean
  late: boolean
  questions: QuizQuestion[]
  answers: QuizAnswers
  score: number | null
  max_score: number
  points_awarded: number
  grading_status: GradingStatus
  grading_error: string | null
  results: QuizResult[] | null
}

export interface QuizLeaderRow {
  rank: number
  user_id: number
  name: string
  points: number
  quizzes_taken: number
}

export interface DropPreview {
  week_key: string
  dry_run: boolean
  message: string
  notes_missing: boolean
  summary_ready: boolean
  projects: string[]
  monthly: boolean
  sent: number
  recipients: { user_id: number; name: string; status: string }[]
}

// --- Admin: learning materials and quiz review (backend/app/schemas_materials.py) ---

export interface Material {
  id: number
  title: string
  kind: 'text' | 'url' | 'file'
  module: string
  week_key: string | null
  specialization: string | null
  status: 'active' | 'archived'
  source_url: string | null
  original_filename: string | null
  char_count: number
  digest_ready: boolean
  digest_error: string | null
  created_at: string
}

export interface MaterialDetail extends Material {
  content_text: string
  digest: string | null
  quiz_ids: number[]
}

export interface AdminQuestion {
  id: string
  type: 'mcq' | 'short'
  difficulty: number
  prompt: string
  options: string[] | null
  answer_key: number | string
  explanation: string
  points: number
}

export interface AdminQuiz {
  id: number
  kind: QuizKind
  period_key: string
  specialization: string | null
  duration_minutes: number
  status: 'generating' | 'failed' | 'draft' | 'published'
  error: string | null
  question_count: number
  attempts: number
  sources: { id: number; title: string }[]
  created_at: string
}

export interface AdminQuizDetail extends AdminQuiz {
  questions: AdminQuestion[]
}

// --- Coding exercises (backend/app/schemas_coding.py) ---

export interface ExerciseSummary {
  id: number
  title: string
  language: 'python' | 'javascript'
  difficulty: number
  points: number
  module: string
  week_key: string | null
  solved: boolean
  verified: boolean
  points_earned: number
  attempts: number
}

export interface CodeAttempt {
  id: number
  exercise_id: number
  passed_count: number
  total_count: number
  runner: 'browser' | 'remote'
  verified: boolean
  results: { name: string; passed: boolean; actual: string | null; error: string | null }[] | null
  runner_error: string | null
  grading_status: GradingStatus
  ai_feedback: string | null
  points_awarded: number
  created_at: string
}

export interface ExerciseDetail extends ExerciseSummary {
  description_md: string
  starter_code: string
  entrypoint: string
  time_limit_seconds: number
  visible_tests: { name: string; args: unknown[]; expected: unknown }[]
  hidden_test_count: number
  draft: string | null
  draft_updated_at: string | null
  runner: 'browser' | 'remote'
  unverified_points: number
  recent_attempts: CodeAttempt[]
}

export interface AdminExercise {
  id: number
  title: string
  description_md: string
  language: 'python' | 'javascript'
  starter_code: string
  entrypoint: string
  tests: { name: string; args: unknown[]; expected: unknown; hidden: boolean }[]
  difficulty: number
  points: number
  module: string
  week_key: string | null
  material_id: number | null
  time_limit_seconds: number
  status: 'draft' | 'published'
  reference_solution: string | null
  tests_verified: boolean
  created_at: string
}

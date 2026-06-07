// Shared TypeScript types mirroring backend Pydantic schemas

export interface QuestionOption {
  value: string
  label: string
}

export interface CollectQuestion {
  id: string
  prompt: string
  options: QuestionOption[]
}

export interface Step1Answers {
  companion: string
  group_size: string
  location: string
  scene: string
  budget: string
  duration: string
}

export interface HardConstraints {
  max_distance_km: number
  age_range: [number, number]
  total_duration: number
}

export interface SoftPreferences {
  noise_level: string
  per_capita: number
  tags: string[]
}

export interface ConstraintSet {
  hard: HardConstraints
  soft: SoftPreferences
}

export interface TransitInfo {
  mode: string
  duration_min: number
  distance_km: number
}

export interface ItineraryNode {
  node_id: string
  node_type: string
  name: string
  address: string
  start_time: string
  end_time: string
  duration_min: number
  per_capita: number
  transit_to_next: TransitInfo | null
  // POI enrichment fields for rich-media card rendering
  image_url?: string
  tags?: string[]
  description?: string
  rating?: number
  review_count?: number
}

export interface Itinerary {
  session_id: string
  nodes: ItineraryNode[]
  total_duration_min: number
  total_per_capita: number
}

// SSE event types from POST /api/plan/run
export type PlanEvent =
  | { type: 'thought'; content: string }
  | { type: 'action'; content?: string; tool?: string; params?: Record<string, unknown> }
  | { type: 'observation'; content?: string; tool?: string; result?: Record<string, unknown> }
  | { type: 'done'; itinerary: Itinerary; content?: string }
  | { type: 'error'; content: string; error?: string }

// SSE event types from POST /api/execute
export type ExecuteEvent =
  | { type: 'start'; session_id: string; total: number }
  | { type: 'booking'; index: number; node_id: string; name: string; status: 'success' | 'failed'; order_id: string; message: string }
  | { type: 'complete'; session_id: string; success_count: number; failed_count: number; confirmation_text: string }

export type CollabState = 'pending' | 'all_confirmed' | 'executing' | 'done'

export interface SharedPlan {
  token: string
  itinerary: Itinerary
  owner_id: string
  member_ids: string[]
  contested_nodes: number[]
  confirmed_users: string[]
  state: CollabState
  expires_at: string
}

// User profile (flywheel memory)
export interface UserProfile {
  user_id: string
  name: string
  avatar: string
  preference_tags: string[]
  preference_summary: string
  is_returning?: boolean
}

// App phase flow
export type AppPhase =
  | 'login'
  | 'collect'
  | 'planning'
  | 'itinerary'
  | 'collab'
  | 'execute'
  | 'done'

export interface AppState {
  phase: AppPhase
  sessionId: string
  userId: string
  userProfile: UserProfile | null
  constraintSet: ConstraintSet | null
  itinerary: Itinerary | null
  collabToken: string | null
  confirmationText: string
  learningLog: string[]
  extractedTags: string[]
  preferenceSummary: string
}

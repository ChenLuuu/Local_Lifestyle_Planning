// API client for backend endpoints
import type {
  CollectQuestion,
  ConstraintSet,
  Itinerary,
  ItineraryNode,
  SharedPlan,
  Step1Answers,
  UserProfile,
} from './types'

const BASE = '/api'

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`${res.status} ${err}`)
  }
  return res.json() as Promise<T>
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json() as Promise<T>
}

// Auth: fixed login as 小团
export async function loginUser(): Promise<UserProfile> {
  return post<UserProfile>('/auth/login', {})
}

// Profile: get user profile
export async function getUserProfile(userId: string): Promise<UserProfile> {
  return get<UserProfile>(`/profile/${userId}`)
}

// F01: Get step-1 questions
export async function fetchQuestions(): Promise<CollectQuestion[]> {
  return get<CollectQuestion[]>('/collect/questions')
}

// F02: Get word-cloud tags from step-1 answers
export async function fetchTags(answers: Step1Answers): Promise<string[]> {
  const res = await post<{ tags: string[] }>('/collect/tags', {
    companion: answers.companion,
    scene: answers.scene,
  })
  return res.tags
}

// F02: Submit all 3 steps and get ConstraintSet + extracted preferences
export async function submitCollection(
  answers: Step1Answers,
  selectedTags: string[],
  freeText: string,
  _sessionId: string,
  userId: string = '',
): Promise<{ constraintSet: ConstraintSet; extractedTags: string[]; preferenceSummary: string }> {
  const res = await post<{
    status: string
    constraint_set: ConstraintSet
    extracted_tags: string[]
    preference_summary: string
  }>('/collect/complete', {
    step1: answers,
    step2: { tags: selectedTags },
    step3: { special_requirements: freeText },
    user_id: userId,
  })
  return {
    constraintSet: res.constraint_set,
    extractedTags: res.extracted_tags ?? [],
    preferenceSummary: res.preference_summary ?? '',
  }
}

// F05: Get swap candidates for a node
export async function fetchSwapCandidates(
  sessionId: string,
  itinerary: Itinerary,
  nodeIndex: number,
  constraintSet: ConstraintSet,
): Promise<ItineraryNode[]> {
  const res = await post<{ candidates: ItineraryNode[] }>('/plan/swap/candidates', {
    session_id: sessionId,
    itinerary,
    node_index: nodeIndex,
    constraint_set: constraintSet,
  })
  return res.candidates
}

// F05: Accept a swap candidate
export async function acceptSwap(
  sessionId: string,
  itinerary: Itinerary,
  nodeIndex: number,
  candidate: ItineraryNode,
  constraintSet: ConstraintSet,
): Promise<Itinerary> {
  const res = await post<{ itinerary: Itinerary }>('/plan/swap/accept', {
    session_id: sessionId,
    itinerary,
    node_index: nodeIndex,
    candidate,
    constraint_set: constraintSet,
  })
  return res.itinerary
}

// F08: Create share link
export async function createShareLink(
  itinerary: Itinerary,
  ownerId: string,
  memberIds: string[],
): Promise<{ token: string; share_url: string }> {
  return post('/collab/share', { itinerary, owner_id: ownerId, member_ids: memberIds })
}

// F08: Get shared plan by token
export async function getSharedPlan(token: string): Promise<SharedPlan> {
  return get<SharedPlan>(`/collab/plan/${token}`)
}

// F08: Cast a vote
export async function castVote(
  token: string,
  userId: string,
  nodeIndex: number,
  approved: boolean,
  comment: string,
): Promise<SharedPlan> {
  return post<SharedPlan>('/collab/vote', {
    token,
    user_id: userId,
    node_index: nodeIndex,
    approved,
    comment,
  })
}

// F08: Mark confirmed
export async function markConfirmed(token: string, userId: string): Promise<SharedPlan> {
  return post<SharedPlan>('/collab/confirm', { token, user_id: userId })
}

// F08: Advance state
export async function advanceState(token: string, newState: string): Promise<SharedPlan> {
  return post<SharedPlan>('/collab/advance', { token, new_state: newState })
}

import { useState } from 'react'
import type { AppPhase, AppState, ConstraintSet, Itinerary, UserProfile } from './types'
import LoginPage from './components/LoginPage'
import CollectPage from './components/CollectPage'
import PlanningPage from './components/PlanningPage'
import ItineraryPage from './components/ItineraryPage'
import CollabPage from './components/CollabPage'
import ExecutePage from './components/ExecutePage'
import DonePage from './components/DonePage'

const SESSION_ID = `session_${Date.now()}`

const PHASE_LABELS: Record<AppPhase, string> = {
  login: '登录',
  collect: '告诉我',
  planning: '规划中',
  itinerary: '确认',
  collab: '协同',
  execute: '执行',
  done: '完成',
}

const PHASE_ICONS: Record<AppPhase, string> = {
  login: '🐻',
  collect: '📝',
  planning: '🧠',
  itinerary: '🗺️',
  collab: '👥',
  execute: '🚀',
  done: '🎉',
}

// Phases shown in the stepper (login and done excluded)
const STEPPER_PHASES: AppPhase[] = ['collect', 'planning', 'itinerary', 'collab', 'execute']

export default function App() {
  const [state, setState] = useState<AppState>({
    phase: 'login',
    sessionId: SESSION_ID,
    userId: '',
    userProfile: null,
    constraintSet: null,
    itinerary: null,
    collabToken: null,
    confirmationText: '',
    learningLog: [],
    extractedTags: [],
    preferenceSummary: '',
  })

  const setPhase = (phase: AppPhase) => setState(s => ({ ...s, phase }))

  const onLoginDone = (profile: UserProfile) => {
    setState(s => ({
      ...s,
      userId: profile.user_id,
      userProfile: profile,
      phase: 'collect',
    }))
  }

  const onCollectDone = (
    cs: ConstraintSet,
    extractedTags: string[],
    preferenceSummary: string,
  ) => {
    setState(s => ({
      ...s,
      constraintSet: cs,
      extractedTags,
      preferenceSummary,
      phase: 'planning',
    }))
  }

  const onPlanDone = (itinerary: Itinerary) => {
    setState(s => ({ ...s, itinerary, phase: 'itinerary' }))
  }

  const onItineraryDone = (itinerary: Itinerary) => {
    setState(s => ({ ...s, itinerary, phase: 'collab' }))
  }

  const onCollabDone = (token: string | null, itinerary: Itinerary) => {
    setState(s => ({ ...s, collabToken: token, itinerary, phase: 'execute' }))
  }

  const onExecuteDone = (confirmationText: string, learningLog: string[]) => {
    setState(s => ({ ...s, confirmationText, learningLog, phase: 'done' }))
  }

  const onRestart = () => {
    setState(s => ({
      phase: 'collect',
      sessionId: `session_${Date.now()}`,
      userId: s.userId,
      userProfile: s.userProfile,
      constraintSet: null,
      itinerary: null,
      collabToken: null,
      confirmationText: '',
      learningLog: [],
      extractedTags: [],
      preferenceSummary: '',
    }))
  }

  const isInFlow = STEPPER_PHASES.includes(state.phase as AppPhase)
  const currentStepperIdx = STEPPER_PHASES.indexOf(state.phase as AppPhase)

  return (
    <div className="min-h-screen bg-orange-50/40">
      {/* Header */}
      <header className="bg-white sticky top-0 z-10 shadow-sm">
        <div className="max-w-2xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-brand-orange rounded-xl flex items-center justify-center text-white text-base shadow-sm shadow-orange-200">
              🗺️
            </div>
            <span className="font-bold text-gray-800 text-base">本地活动规划</span>
          </div>

          {/* User badge (shown after login) */}
          {state.userProfile && (
            <div className="flex items-center gap-1.5">
              {/* Stepper — only in flow phases */}
              {isInFlow && (
                <div className="flex items-center gap-1 mr-2">
                  {STEPPER_PHASES.map((p, i) => (
                    <div key={p} className="flex items-center">
                      <div
                        className={`flex items-center justify-center rounded-full text-xs transition-all duration-300 ${
                          i < currentStepperIdx
                            ? 'w-5 h-5 bg-brand-orange text-white font-bold'
                            : i === currentStepperIdx
                              ? 'w-6 h-6 bg-brand-orange text-white font-bold shadow-md shadow-orange-200 ring-2 ring-orange-100 ring-offset-1'
                              : 'w-4 h-4 bg-gray-100 text-gray-400'
                        }`}
                        title={PHASE_LABELS[p]}
                      >
                        {i < currentStepperIdx ? '✓' : PHASE_ICONS[p]}
                      </div>
                      {i < STEPPER_PHASES.length - 1 && (
                        <div className={`w-2.5 h-0.5 mx-0.5 rounded-full transition-colors ${i < currentStepperIdx ? 'bg-brand-orange' : 'bg-gray-200'}`} />
                      )}
                    </div>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-1 bg-orange-50 border border-orange-100 rounded-full px-2.5 py-1">
                <span className="text-sm">{state.userProfile.avatar}</span>
                <span className="text-xs font-medium text-brand-orange">{state.userProfile.name}</span>
              </div>
            </div>
          )}
        </div>
        <div className="h-0.5 bg-brand-orange" />
      </header>

      {/* Phase label (not on login) */}
      {state.phase !== 'login' && (
        <div className="max-w-2xl mx-auto px-4 pt-4">
          <div className="inline-flex items-center gap-1.5 bg-white rounded-full px-3 py-1 shadow-sm border border-orange-100">
            <span className="text-sm">{PHASE_ICONS[state.phase]}</span>
            <p className="text-xs font-semibold text-brand-orange">{PHASE_LABELS[state.phase]}</p>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="max-w-2xl mx-auto px-4 py-4 pb-16">
        {state.phase === 'login' && (
          <LoginPage onDone={onLoginDone} />
        )}
        {state.phase === 'collect' && (
          <CollectPage
            sessionId={state.sessionId}
            userId={state.userId}
            userProfile={state.userProfile}
            onDone={onCollectDone}
          />
        )}
        {state.phase === 'planning' && state.constraintSet && (
          <PlanningPage
            sessionId={state.sessionId}
            userId={state.userId}
            constraintSet={state.constraintSet}
            onDone={onPlanDone}
          />
        )}
        {state.phase === 'itinerary' && state.itinerary && state.constraintSet && (
          <ItineraryPage
            sessionId={state.sessionId}
            itinerary={state.itinerary}
            constraintSet={state.constraintSet}
            onDone={onItineraryDone}
            onBack={() => setPhase('planning')}
          />
        )}
        {state.phase === 'collab' && state.itinerary && (
          <CollabPage
            sessionId={state.sessionId}
            itinerary={state.itinerary}
            onDone={onCollabDone}
            onSkip={() => onCollabDone(null, state.itinerary!)}
          />
        )}
        {state.phase === 'execute' && state.itinerary && (
          <ExecutePage
            sessionId={state.sessionId}
            itinerary={state.itinerary}
            onDone={onExecuteDone}
          />
        )}
        {state.phase === 'done' && (
          <DonePage
            confirmationText={state.confirmationText}
            learningLog={state.learningLog}
            onRestart={onRestart}
          />
        )}
      </main>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ConstraintSet, Itinerary, PlanEvent } from '../types'

interface Props {
  sessionId: string
  userId?: string
  constraintSet: ConstraintSet
  onDone: (itinerary: Itinerary) => void
}

const THINKING_STEPS = [
  { icon: '🔍', text: '正在分析你的偏好…' },
  { icon: '📍', text: '正在搜索周边优质场地…' },
  { icon: '🍜', text: '正在匹配美食与活动…' },
  { icon: '🗺️', text: '正在规划最优路线…' },
  { icon: '⏱️', text: '正在计算时间安排…' },
  { icon: '✨', text: 'AI 精细化规划中…' },
  { icon: '🎯', text: '即将完成，马上出发！' },
]

export default function PlanningPage({ sessionId, userId = '', constraintSet, onDone }: Props) {
  const [stepIdx, setStepIdx] = useState(0)
  const [status, setStatus] = useState<'streaming' | 'done' | 'error'>('streaming')
  const [errorMsg, setErrorMsg] = useState('')
  const doneRef = useRef(false)

  useEffect(() => {
    if (status !== 'streaming') return
    const interval = setInterval(() => {
      setStepIdx(i => Math.min(i + 1, THINKING_STEPS.length - 1))
    }, 2200)
    return () => clearInterval(interval)
  }, [status])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    async function startPlanning() {
      try {
        const res = await fetch('/api/plan/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            constraint_set: constraintSet,
            session_id: sessionId,
            start_time: '10:00',
            user_id: userId,
          }),
          signal: controller.signal,
        })

        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done || cancelled) break
          buf += decoder.decode(value, { stream: true })

          const lines = buf.split('\n')
          buf = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data:')) continue
            const raw = line.slice(5).trim()
            if (raw === '[DONE]') {
              setStatus('done')
              return
            }
            try {
              const event = JSON.parse(raw) as PlanEvent
              if (event.type === 'done') {
                if (!cancelled && !doneRef.current) {
                  doneRef.current = true
                  onDone(event.itinerary)
                }
                setStatus('done')
                return
              }
              // Intentionally ignore thought/action/observation events — we only show the loading UI
            } catch {
              // ignore parse errors
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setErrorMsg(err instanceof Error ? err.message : '规划失败')
          setStatus('error')
        }
      }
    }

    void startPlanning()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [sessionId, constraintSet, onDone])

  const currentStep = THINKING_STEPS[stepIdx]

  return (
    <div className="flex flex-col items-center justify-center min-h-[65vh] space-y-10 px-4">
      {/* Animated brain icon */}
      <motion.div
        animate={{
          scale: [1, 1.08, 1],
          rotate: [0, 4, -4, 0],
        }}
        transition={{ repeat: Infinity, duration: 3.5, ease: 'easeInOut' }}
        className="relative"
      >
        <div className="w-28 h-28 rounded-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, rgba(255,85,0,0.15) 0%, rgba(255,45,107,0.15) 100%)' }}>
          <div className="w-20 h-20 rounded-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, rgba(255,85,0,0.25) 0%, rgba(255,45,107,0.25) 100%)' }}>
            <span className="text-5xl">🧠</span>
          </div>
        </div>
        {/* Orbiting dots */}
        {[0, 1, 2].map(i => (
          <motion.div
            key={i}
            className="absolute w-3 h-3 rounded-full"
            style={{
              background: (['#FF6200', '#D94A00', '#FF8C42'] as const)[i],
              top: '50%',
              left: '50%',
              marginTop: -6,
              marginLeft: -6,
            }}
            animate={{
              x: Math.cos((i * 2 * Math.PI) / 3) * 60,
              y: Math.sin((i * 2 * Math.PI) / 3) * 60,
              rotate: 360,
            }}
            transition={{
              repeat: Infinity,
              duration: 3,
              delay: i * 1,
              ease: 'linear',
            }}
          />
        ))}
      </motion.div>

      {/* Title + step text */}
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-bold text-gray-800">AI 规划中</h2>
        <AnimatePresence mode="wait">
          <motion.div
            key={stepIdx}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.35 }}
            className="flex items-center justify-center gap-2"
          >
            <span className="text-xl">{currentStep.icon}</span>
            <p className="text-gray-500 text-sm">{currentStep.text}</p>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Bouncing dots loader */}
      <div className="flex gap-2">
        {[0, 1, 2, 3, 4].map(i => (
          <motion.div
            key={i}
            className="w-2 h-2 rounded-full"
            style={{
              background: `hsl(${16 + i * 8}, 90%, ${55 + i * 3}%)`,
            }}
            animate={{ y: [0, -10, 0] }}
            transition={{
              repeat: Infinity,
              duration: 0.9,
              delay: i * 0.12,
              ease: 'easeInOut',
            }}
          />
        ))}
      </div>

      {/* Step progress pills */}
      <div className="flex gap-1.5">
        {THINKING_STEPS.map((_, i) => (
          <motion.div
            key={i}
            className="h-1.5 rounded-full transition-all duration-500"
            style={{ background: i <= stepIdx ? '#FF6200' : '#E5E7EB' }}
            animate={{ width: i === stepIdx ? 28 : 8 }}
          />
        ))}
      </div>

      {/* Error state */}
      {status === 'error' && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="card border-red-100 bg-red-50 text-center max-w-xs w-full"
        >
          <p className="text-sm text-red-600">规划失败：{errorMsg}</p>
          <button
            className="btn-primary mt-3 w-full"
            onClick={() => window.location.reload()}
          >
            重新尝试
          </button>
        </motion.div>
      )}
    </div>
  )
}

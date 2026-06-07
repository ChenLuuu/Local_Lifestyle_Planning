import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { fetchQuestions, fetchTags, submitCollection } from '../api'
import type { CollectQuestion, ConstraintSet, Step1Answers, UserProfile } from '../types'

interface Props {
  sessionId: string
  userId: string
  userProfile: UserProfile | null
  onDone: (cs: ConstraintSet, extractedTags: string[], preferenceSummary: string) => void
}

const OPTION_EMOJI: Record<string, string> = {
  '一个人': '🧘', '另一半': '💑', '闺蜜': '👯', '兄弟': '🍻', '带娃': '👶', '家庭聚会': '👨‍👩‍👧', '商务接待': '💼',
  '1人': '☝️', '2人': '✌️', '3-4人': '👥', '5人以上': '🎉',
  '市中心': '🏙️', '我家附近': '🏠', '目的地周边': '📍', '随便': '🎲',
  '悠闲放松': '😌', '元气打卡': '💪', '文化探索': '🎨', '美食之旅': '🍜', '仪式感出行': '🎂', '商务接待_scene': '💼',
  '人均<50': '💰', '50-100': '💰💰', '100-200': '💰💰💰', '200-500': '💎', '500+': '👑',
  '2小时': '⚡', '半天（4小时）': '🌤️', '大半天（6小时）': '🌇', '全天（8小时）': '🌞',
}

const EMPTY_ANSWERS: Step1Answers = {
  companion: '',
  group_size: '',
  location: '',
  scene: '',
  budget: '',
  duration: '',
}

const DEFAULT_TAGS = ['美食', '出片', '室内', '轻松', '艺术', '商场', '亲子', '约会', '不想走路', '拍照', '网红', '探店']

export default function CollectPage({ sessionId, userId, userProfile, onDone }: Props) {
  const [questions, setQuestions] = useState<CollectQuestion[]>([])
  const [answers, setAnswers] = useState<Step1Answers>(EMPTY_ANSWERS)
  const [tags, setTags] = useState<string[]>(DEFAULT_TAGS)
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set())
  const [freeText, setFreeText] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [extractedTags, setExtractedTags] = useState<string[]>([])

  useEffect(() => {
    fetchQuestions()
      .then(qs => setQuestions(qs))
      .catch(() => setError('加载失败，请刷新重试'))
      .finally(() => setLoading(false))

    fetchTags(EMPTY_ANSWERS)
      .then(ts => { if (ts.length > 0) setTags(ts) })
      .catch(() => { /* keep DEFAULT_TAGS */ })
  }, [])

  const handleSelect = (questionId: string, value: string) => {
    setAnswers(prev => ({ ...prev, [questionId]: value }))
  }

  const toggleTag = (tag: string) => {
    setSelectedTags(prev => {
      const next = new Set(prev)
      next.has(tag) ? next.delete(tag) : next.add(tag)
      return next
    })
  }

  const answeredCount = Object.values(answers).filter(Boolean).length
  const totalQuestions = questions.length || Object.keys(EMPTY_ANSWERS).length
  const canSubmit = answeredCount >= totalQuestions

  const handleSubmit = async () => {
    if (!canSubmit || submitting) return
    setSubmitting(true)
    try {
      const { constraintSet, extractedTags: etags, preferenceSummary } = await submitCollection(
        answers,
        [...selectedTags],
        freeText,
        sessionId,
        userId,
      )
      if (etags.length > 0) {
        setExtractedTags(etags)
        // Brief pause to show extracted tags before transitioning
        await new Promise(r => setTimeout(r, 1400))
      }
      onDone(constraintSet, etags, preferenceSummary)
    } catch {
      setError('提交失败，请重试')
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-48 gap-4">
        <div className="text-3xl animate-bounce">✨</div>
        <div className="flex gap-1.5">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="w-2 h-2 bg-brand-orange rounded-full animate-pulse-dot"
              style={{ animationDelay: `${i * 0.16}s` }}
            />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card text-center py-8">
        <p className="text-red-500 mb-4">{error}</p>
        <button className="btn-primary" onClick={() => window.location.reload()}>刷新页面</button>
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="space-y-5"
    >
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="rounded-2xl p-6 text-center overflow-hidden relative"
        style={{ background: 'linear-gradient(135deg, #FF6200 0%, #D94A00 100%)' }}
      >
        <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-20 h-20 bg-white/10 rounded-full translate-y-1/2 -translate-x-1/2" />
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 200, delay: 0.1 }}
          className="text-5xl mb-3 relative"
        >
          🗺️
        </motion.div>
        <h1 className="text-2xl font-bold text-white relative">告诉我你的计划</h1>
        <p className="text-sm text-white/75 mt-1.5 relative">只需一分钟，AI 帮你搞定完美行程</p>
      </motion.div>

      {/* Saved preferences from profile (flywheel) */}
      {userProfile && userProfile.preference_tags.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-white rounded-2xl p-4 border border-orange-100 shadow-sm"
        >
          <div className="flex items-center gap-2 mb-2.5">
            <span className="text-base">🧠</span>
            <p className="text-xs font-semibold text-brand-orange">已记住你的偏好</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {userProfile.preference_tags.map(tag => (
              <span
                key={tag}
                className="text-xs bg-orange-50 text-orange-600 border border-orange-200 rounded-full px-2.5 py-0.5 font-medium"
              >
                {tag}
              </span>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-2">本次规划将自动融入以上偏好</p>
        </motion.div>
      )}

      {/* Progress indicator */}
      {answeredCount > 0 && answeredCount < totalQuestions && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 px-1">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-brand-orange rounded-full"
              initial={{ width: '0%' }}
              animate={{ width: `${(answeredCount / totalQuestions) * 100}%` }}
              transition={{ ease: 'easeOut' }}
            />
          </div>
          <span className="text-xs text-gray-400 shrink-0">{answeredCount}/{totalQuestions}</span>
        </motion.div>
      )}

      {/* Questions */}
      <div className="card space-y-5">
        <h2 className="text-sm font-bold uppercase tracking-wider text-brand-orange">基本信息</h2>
        {questions.map((q, i) => {
          const selected = answers[q.id as keyof Step1Answers]
          return (
            <motion.div
              key={q.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
            >
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                {q.prompt}
              </label>
              <div className="relative">
                <select
                  value={selected || ''}
                  onChange={e => handleSelect(q.id, e.target.value)}
                  className={`select-field pr-10 ${selected ? 'text-gray-900 border-orange-200 bg-orange-50/30' : ''}`}
                >
                  <option value="" disabled>请选择…</option>
                  {q.options.map(opt => (
                    <option key={opt.value} value={opt.value}>
                      {OPTION_EMOJI[opt.value] !== undefined ? `${OPTION_EMOJI[opt.value]}  ${opt.label}` : opt.label}
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs">
                  ▾
                </div>
                {selected && (
                  <div className="absolute right-8 top-1/2 -translate-y-1/2 text-brand-orange text-sm font-bold">✓</div>
                )}
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Tags */}
      <motion.div
        className="card"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-sm font-bold uppercase tracking-wider text-brand-orange">你在意哪些</h2>
          {selectedTags.size > 0 && (
            <span className="text-xs text-white bg-brand-orange px-2.5 py-0.5 rounded-full font-medium">
              已选 {selectedTags.size}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-400 mb-4">可多选，也可以跳过</p>
        <div className="flex flex-wrap gap-2">
          {tags.map((tag, i) => (
            <motion.button
              key={tag}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.3 + i * 0.04, type: 'spring', stiffness: 400, damping: 20 }}
              whileTap={{ scale: 0.88 }}
              onClick={() => toggleTag(tag)}
              className={selectedTags.has(tag) ? 'tag-selected' : 'tag-unselected'}
            >
              {tag}
            </motion.button>
          ))}
        </div>
      </motion.div>

      {/* Free text */}
      <motion.div
        className="card"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
      >
        <h2 className="text-sm font-bold uppercase tracking-wider mb-1 text-brand-orange">特别要求</h2>
        <p className="text-xs text-gray-400 mb-3">例如：宠物友好、不吃辣、学生党预算</p>
        <textarea
          value={freeText}
          onChange={e => setFreeText(e.target.value)}
          placeholder="没有特别要求可以直接开始规划～"
          rows={3}
          className="w-full bg-gray-50 border border-gray-200 rounded-xl p-3 text-sm resize-none focus:outline-none focus:border-brand-orange focus:ring-2 focus:ring-orange-100 transition-all"
        />
      </motion.div>

      {/* Extracted preference tags toast */}
      <AnimatePresence>
        {extractedTags.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="bg-green-50 border border-green-200 rounded-2xl p-4"
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">✅</span>
              <p className="text-xs font-semibold text-green-700">已从你的描述中提取偏好</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {extractedTags.map(tag => (
                <span
                  key={tag}
                  className="text-xs bg-green-100 text-green-700 border border-green-200 rounded-full px-2.5 py-0.5 font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>
            <p className="text-xs text-green-600 mt-2">已保存至你的个人偏好，下次规划时自动使用</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Submit */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="space-y-2 pb-4"
      >
        <button
          className="btn-primary w-full text-base py-4"
          onClick={handleSubmit}
          disabled={!canSubmit || submitting}
        >
          {submitting ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              正在整理需求…
            </span>
          ) : (
            '🚀 开始智能规划'
          )}
        </button>
        {!canSubmit && answeredCount < totalQuestions && (
          <p className="text-center text-xs text-gray-400">
            还差 {totalQuestions - answeredCount} 个问题未填写
          </p>
        )}
      </motion.div>
    </motion.div>
  )
}

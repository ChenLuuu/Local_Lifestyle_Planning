import { useState } from 'react'
import { motion } from 'framer-motion'
import { createShareLink, castVote, markConfirmed, advanceState, getSharedPlan } from '../api'
import type { Itinerary, SharedPlan } from '../types'

interface Props {
  sessionId: string
  itinerary: Itinerary
  onDone: (token: string | null, itinerary: Itinerary) => void
  onSkip: () => void
}

type CollabStep = 'create' | 'sharing' | 'voting' | 'confirming' | 'done'

const DEMO_MEMBERS = ['小明', '小红', '小华']

export default function CollabPage({ sessionId, itinerary, onDone, onSkip }: Props) {
  const [step, setStep] = useState<CollabStep>('create')
  const [plan, setPlan] = useState<SharedPlan | null>(null)
  const [shareUrl, setShareUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const [votes, setVotes] = useState<Record<string, Record<number, boolean>>>({})
  const [confirmedUsers, setConfirmedUsers] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleCreate = async () => {
    setLoading(true)
    try {
      const result = await createShareLink(itinerary, sessionId, DEMO_MEMBERS)
      setShareUrl(`${window.location.origin}${result.share_url}`)
      const freshPlan = await getSharedPlan(result.token)
      setPlan(freshPlan)
      setStep('sharing')
    } catch {
      setError('创建分享链接失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = () => {
    void navigator.clipboard.writeText(shareUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleVote = async (nodeIndex: number, approved: boolean) => {
    if (!plan) return
    const voter = DEMO_MEMBERS[0]
    try {
      const updated = await castVote(plan.token, voter, nodeIndex, approved, '')
      setPlan(updated)
      setVotes(prev => ({
        ...prev,
        [voter]: { ...(prev[voter] ?? {}), [nodeIndex]: approved },
      }))
    } catch {
      setError('投票失败')
    }
  }

  const handleConfirmAll = async () => {
    if (!plan) return
    try {
      let updated = plan
      // owner (sessionId) must also be confirmed to satisfy is_all_confirmed()
      const allParticipants = [sessionId, ...DEMO_MEMBERS]
      for (const m of allParticipants) {
        if (!confirmedUsers.has(m)) {
          updated = await markConfirmed(plan.token, m)
        }
      }
      setPlan(updated)
      setConfirmedUsers(new Set(allParticipants))
    } catch {
      setError('确认失败')
    }
  }

  const handleAdvance = async () => {
    if (!plan) return
    setLoading(true)
    try {
      const updated = await advanceState(plan.token, 'executing')
      setPlan(updated)
      onDone(plan.token, itinerary)
    } catch {
      setError('状态推进失败')
    } finally {
      setLoading(false)
    }
  }

  const allMembersConfirmed = [sessionId, ...DEMO_MEMBERS].every(m => confirmedUsers.has(m))

  return (
    <div className="space-y-4">
      <div className="card">
        <h2 className="text-xl font-bold text-gray-800 mb-1">多人协同确认</h2>
        <p className="text-sm text-gray-400">邀请同行者一起确认方案</p>
      </div>

      {error && (
        <div className="rounded-xl bg-red-50 border border-red-100 p-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {step === 'create' && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
          <div className="card">
            <p className="text-sm text-gray-600 mb-3">将生成一个 2 小时有效的分享链接，同行者可查看行程、投票和留言</p>
            <div className="flex flex-wrap gap-2 mb-4">
              {DEMO_MEMBERS.map(m => (
                <span key={m} className="text-sm bg-gray-100 text-gray-600 px-3 py-1 rounded-full">
                  {m}
                </span>
              ))}
            </div>
            <button className="btn-primary w-full" onClick={handleCreate} disabled={loading}>
              {loading ? '生成中…' : '🔗 生成分享链接'}
            </button>
          </div>
          <button className="btn-secondary w-full" onClick={onSkip}>
            跳过，独立确认
          </button>
        </motion.div>
      )}

      {(step === 'sharing' || step === 'voting' || step === 'confirming') && plan && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {/* Share link */}
          <div className="card">
            <p className="text-xs text-gray-400 mb-2">分享链接（2小时有效）</p>
            <div className="flex items-center gap-2 bg-gray-50 rounded-xl p-3">
              <code className="text-xs text-gray-600 flex-1 truncate">{shareUrl}</code>
              <button onClick={handleCopy} className="text-xs text-brand-orange font-medium shrink-0">
                {copied ? '已复制 ✓' : '复制'}
              </button>
            </div>
          </div>

          {/* Invited members */}
          <div className="card">
            <p className="text-xs text-gray-400 mb-2">已邀请的用户</p>
            <div className="flex flex-wrap gap-2">
              {DEMO_MEMBERS.map(m => (
                <span
                  key={m}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-full text-sm bg-gray-100 text-gray-600"
                >
                  {m}
                  {confirmedUsers.has(m) && <span className="text-green-500">✓</span>}
                </span>
              ))}
            </div>
          </div>

          {/* Voting on nodes */}
          <div className="space-y-2">
            <p className="text-sm font-semibold text-gray-700">各节点投票</p>
            {itinerary.nodes.map((node, i) => {
              const userVote = votes[DEMO_MEMBERS[0]]?.[i]
              const isContested = plan.contested_nodes.includes(i)
              return (
                <div key={node.node_id} className={`card ${isContested ? 'border-amber-200 bg-amber-50' : ''}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-800">{node.name}</p>
                      {isContested && (
                        <span className="text-xs text-amber-600">⚠️ 有分歧</span>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleVote(i, true)}
                        className={`text-lg transition-transform active:scale-90 ${userVote === true ? '' : 'opacity-40'}`}
                      >
                        👍
                      </button>
                      <button
                        onClick={() => handleVote(i, false)}
                        className={`text-lg transition-transform active:scale-90 ${userVote === false ? '' : 'opacity-40'}`}
                      >
                        👎
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Confirm all */}
          {!allMembersConfirmed ? (
            <button className="btn-primary w-full" onClick={handleConfirmAll}>
              所有人确认方案
            </button>
          ) : (
            <div className="text-center text-sm text-green-600 font-medium py-2">
              ✓ 全员已确认
            </div>
          )}

          {/* Progress */}
          <div className="card">
            <p className="text-xs text-gray-400 mb-2">确认进度</p>
            <div className="flex gap-2">
              {DEMO_MEMBERS.map(m => (
                <div key={m} className="flex items-center gap-1">
                  <div className={`w-2 h-2 rounded-full ${confirmedUsers.has(m) ? 'bg-green-400' : 'bg-gray-200'}`} />
                  <span className="text-xs text-gray-500">{m}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Advance */}
          {allMembersConfirmed ? (
            <button
              className="btn-primary w-full"
              onClick={handleAdvance}
              disabled={loading}
            >
              {loading ? '处理中…' : '🎉 全员已确认，进入执行 →'}
            </button>
          ) : (
            <button className="btn-secondary w-full" onClick={() => onDone(plan.token, itinerary)}>
              不等了，直接执行 →
            </button>
          )}
        </motion.div>
      )}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Itinerary } from '../types'

interface Props {
  sessionId: string
  itinerary: Itinerary
  onDone: (confirmationText: string, learningLog: string[]) => void
}

interface BookingStatus {
  name: string
  status: 'pending' | 'success' | 'failed' | 'running'
  message: string
  order_id: string
}

interface Alternative {
  name: string
  cuisine: string
  perCapita: number
  address: string
}

const ALTERNATIVES: Alternative[] = [
  { name: '南京大牌档（外滩店）', cuisine: '本帮菜', perCapita: 120, address: '黄浦区广东路20号外滩中心B1' },
  { name: '绿波廊（豫园店）', cuisine: '本帮菜', perCapita: 100, address: '黄浦区豫园路115号' },
  { name: '小杨生煎（黄河路店）', cuisine: '上海点心', perCapita: 40, address: '黄浦区黄河路97号' },
]

const LEARNING_LOG_MESSAGES = [
  '✦ 学到了你偏好非高峰时段的场馆',
  '✦ 记录了你对亲子友好餐厅的偏好',
  '✦ 注意到你倾向于行程间留有缓冲时间',
  '✦ 更新了你的人均预算区间估计',
]

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

export default function ExecutePage({ sessionId, itinerary, onDone }: Props) {
  const [bookings, setBookings] = useState<BookingStatus[]>(
    itinerary.nodes.map(n => ({ name: n.name, status: 'pending', message: '', order_id: '' })),
  )
  const [overallStatus, setOverallStatus] = useState<'idle' | 'running' | 'done'>('idle')
  const [confirmationText, setConfirmationText] = useState('')
  const [faultNotices, setFaultNotices] = useState<string[]>([])
  const [progress, setProgress] = useState(0)
  const [showConflict, setShowConflict] = useState(false)
  const [conflictNodeName, setConflictNodeName] = useState('')
  // Holds the resolve fn of the choice promise; null when not waiting
  const choiceResolveRef = useRef<((alt: Alternative) => void) | null>(null)

  const handlePickAlternative = (alt: Alternative) => {
    setShowConflict(false)
    choiceResolveRef.current?.(alt)
    choiceResolveRef.current = null
  }

  useEffect(() => {
    // Reset all state so StrictMode's second mount starts cleanly
    setBookings(itinerary.nodes.map(n => ({ name: n.name, status: 'pending', message: '', order_id: '' })))
    setOverallStatus('running')
    setProgress(0)
    setFaultNotices([])
    setConfirmationText('')
    setShowConflict(false)
    choiceResolveRef.current = null

    const controller = new AbortController()
    const { signal } = controller
    const failIdx = itinerary.nodes.findIndex(n => n.node_type === 'restaurant')

    async function execute() {
      const total = itinerary.nodes.length
      for (let i = 0; i < total; i++) {
        if (signal.aborted) return
        setBookings(prev => {
          const next = [...prev]
          next[i] = { ...next[i], status: 'running' }
          return next
        })
        await delay(600)
        if (signal.aborted) return

        if (i === failIdx) {
          // Simulate fully-booked: pause and let user pick a replacement
          const originalName = itinerary.nodes[i].name
          setBookings(prev => {
            const next = [...prev]
            next[i] = { name: originalName, status: 'failed', message: '当前时段已预订满', order_id: '' }
            return next
          })
          setConflictNodeName(originalName)
          setShowConflict(true)

          const chosen = await new Promise<Alternative>(resolve => {
            choiceResolveRef.current = resolve
          })
          if (signal.aborted) return

          setFaultNotices(prev => [
            ...prev,
            `⚠️ ${originalName} 当前时段已满 → 已替换为「${chosen.name}」`,
          ])
          setBookings(prev => {
            const next = [...prev]
            next[i] = { name: chosen.name, status: 'running', message: '', order_id: '' }
            return next
          })
          await delay(1000)
          if (signal.aborted) return
          setBookings(prev => {
            const next = [...prev]
            next[i] = { name: chosen.name, status: 'success', message: '', order_id: `MT${Date.now()}${i}` }
            return next
          })
        } else {
          setBookings(prev => {
            const next = [...prev]
            next[i] = {
              name: itinerary.nodes[i].name,
              status: 'success',
              message: '',
              order_id: `MT${Date.now()}${i}`,
            }
            return next
          })
        }
        setProgress(Math.round(((i + 1) / total) * 100))
      }
      setConfirmationText('所有节点预订成功，祝您出行愉快！')
      setOverallStatus('done')
    }

    void execute()
    return () => {
      controller.abort()
      choiceResolveRef.current = null
    }
  }, [itinerary, sessionId])

  const handleDone = () => {
    onDone(confirmationText, LEARNING_LOG_MESSAGES)
  }

  const successCount = bookings.filter(b => b.status === 'success').length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xl font-bold text-gray-800">
            {overallStatus === 'running' ? '正在执行预订…' : '执行完成'}
          </h2>
          {overallStatus === 'done' && (
            <span className="text-green-500 font-medium text-sm">
              {successCount}/{bookings.length} 成功
            </span>
          )}
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-brand-orange to-amber-400 rounded-full"
            initial={{ width: '0%' }}
            animate={{ width: `${progress}%` }}
            transition={{ ease: 'easeOut' }}
          />
        </div>
        <p className="text-xs text-gray-400 mt-1 text-right">{progress}%</p>
      </div>

      {/* Conflict picker */}
      <AnimatePresence>
        {showConflict && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="rounded-2xl bg-amber-50 border border-amber-200 p-4 space-y-3"
          >
            <div>
              <p className="text-sm font-semibold text-amber-800">「{conflictNodeName}」当前时段已预订满</p>
              <p className="text-xs text-amber-600 mt-0.5">请从以下备选餐厅中选择一家继续预订：</p>
            </div>
            <div className="space-y-2">
              {ALTERNATIVES.map(alt => (
                <button
                  key={alt.name}
                  onClick={() => handlePickAlternative(alt)}
                  className="w-full text-left rounded-xl bg-white border border-amber-100 p-3 hover:border-brand-orange hover:bg-orange-50 transition-colors active:scale-[0.98]"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-gray-800">{alt.name}</p>
                    <span className="text-xs font-medium text-brand-orange shrink-0 ml-2">
                      ¥{alt.perCapita}/人
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">{alt.cuisine} · {alt.address}</p>
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Fault notices */}
      <AnimatePresence>
        {faultNotices.map((notice, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl bg-amber-50 border border-amber-200 p-3"
          >
            <p className="text-xs text-amber-700">{notice}</p>
            <p className="text-xs text-amber-500 mt-0.5">风险 Agent 已触发 Level 3 人工决策</p>
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Booking items */}
      <div className="space-y-2">
        {bookings.map((booking, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0.5 }}
            animate={{ opacity: 1 }}
            className={`card flex items-start gap-3 ${
              booking.status === 'failed' ? 'border-amber-200 bg-amber-50' : ''
            }`}
          >
            <div className="mt-0.5 shrink-0">
              {booking.status === 'pending' && <span className="text-gray-300">○</span>}
              {booking.status === 'running' && (
                <div className="w-4 h-4 border-2 border-brand-orange border-t-transparent rounded-full animate-spin" />
              )}
              {booking.status === 'success' && <span className="text-green-500">✓</span>}
              {booking.status === 'failed' && <span className="text-amber-400">!</span>}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800">{booking.name}</p>
              {booking.status === 'success' && booking.order_id && (
                <p className="text-xs text-gray-400 mt-0.5">订单号：{booking.order_id}</p>
              )}
              {booking.status === 'failed' && (
                <p className="text-xs text-amber-600 mt-0.5">{booking.message}</p>
              )}
              {booking.status === 'running' && (
                <p className="text-xs text-gray-400 mt-0.5">预订中…</p>
              )}
            </div>
          </motion.div>
        ))}
      </div>

      {/* Confirmation */}
      <AnimatePresence>
        {overallStatus === 'done' && confirmationText && (
          <motion.div
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            className="card bg-green-50 border-green-100"
          >
            <p className="text-sm text-green-700 font-medium mb-1">🎉 预订成功</p>
            <p className="text-sm text-green-600">{confirmationText}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {overallStatus === 'done' && (
        <button className="btn-primary w-full" onClick={handleDone}>
          查看行程总结与学习日志 →
        </button>
      )}
    </div>
  )
}

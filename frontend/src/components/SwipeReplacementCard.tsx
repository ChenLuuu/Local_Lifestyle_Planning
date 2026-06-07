import { useRef } from 'react'
import { motion, useMotionValue, useTransform, AnimatePresence } from 'framer-motion'
import type { ItineraryNode } from '../types'

interface Props {
  candidate: ItineraryNode
  originalName: string
  candidateIdx: number
  totalCandidates: number
  onAccept: () => void
  onSkip: () => void
  onCancel: () => void
}

function formatTime(timeStr: string) {
  return timeStr.slice(0, 5)
}

function getPlaceholderImage(node: ItineraryNode): string {
  if (node.image_url) return node.image_url
  const seed = encodeURIComponent(node.name + node.node_type + 'alt')
  return `https://picsum.photos/seed/${seed}/400/300`
}

const DEFAULT_DESCRIPTIONS: Record<string, string> = {
  restaurant: '精选口碑餐厅，环境舒适，菜品精致，是本地食客推荐的地道之选。',
  venue: '热门打卡地标，空间开阔，设施完善，适合拍照留念与沉浸式体验。',
  activity: '趣味互动体验，节奏轻松，氛围活跃，是不可错过的本地特色活动。',
  transport: '便捷交通节点，衔接顺畅，为您的行程提供高效中转服务。',
  shopping: '精选购物场所，品类丰富，价格合理，满足一站式采买需求。',
  default: '精心推荐的地点，为您打造独一无二的本地生活体验。',
}

const SWIPE_THRESHOLD = 100

export default function SwipeReplacementCard({
  candidate,
  originalName,
  candidateIdx,
  totalCandidates,
  onAccept,
  onSkip,
  onCancel,
}: Props) {
  const x = useMotionValue(0)
  const rotate = useTransform(x, [-200, 0, 200], [-20, 0, 20])
  const acceptOpacity = useTransform(x, [0, SWIPE_THRESHOLD], [0, 1])
  const skipOpacity = useTransform(x, [-SWIPE_THRESHOLD, 0], [1, 0])
  const cardScale = useTransform(x, [-200, 0, 200], [0.95, 1, 0.95])

  const exitX = useRef(0)
  const exiting = useRef(false)

  const handleDragEnd = (_: unknown, info: { offset: { x: number } }) => {
    if (exiting.current) return
    if (info.offset.x > SWIPE_THRESHOLD) {
      exiting.current = true
      exitX.current = 400
      setTimeout(onAccept, 250)
    } else if (info.offset.x < -SWIPE_THRESHOLD) {
      exiting.current = true
      exitX.current = -400
      setTimeout(onSkip, 250)
    }
  }

  const imageUrl = getPlaceholderImage(candidate)
  const description = candidate.description ?? DEFAULT_DESCRIPTIONS[candidate.node_type] ?? DEFAULT_DESCRIPTIONS.default
  const tags = candidate.tags ?? ['替补推荐']

  return (
    <AnimatePresence>
      <motion.div
        key={`swipe-overlay-${candidateIdx}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 flex flex-col items-center justify-center bg-black/50 backdrop-blur-sm z-40 px-4"
        onClick={(e) => {
          // Close on backdrop click
          if (e.target === e.currentTarget) onCancel()
        }}
      >
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-4"
        >
          <p className="text-white/80 text-sm mb-1">
            正在为「{originalName}」寻找替补
          </p>
          <div className="flex items-center justify-center gap-1.5">
            {Array.from({ length: totalCandidates }).map((_, i) => (
              <div
                key={i}
                className={`w-2 h-2 rounded-full transition-colors ${
                  i === candidateIdx ? 'bg-white' : 'bg-white/30'
                }`}
              />
            ))}
          </div>
        </motion.div>

        {/* Swipe card */}
        <motion.div
          key={candidate.node_id}
          style={{ x, rotate, scale: cardScale }}
          drag="x"
          dragConstraints={{ left: -250, right: 250 }}
          dragElastic={0.9}
          onDragEnd={handleDragEnd}
          whileDrag={{ cursor: 'grabbing' }}
          animate={
            exiting.current
              ? { x: exitX.current, opacity: 0, transition: { duration: 0.25, ease: 'easeOut' } }
              : { x: 0, opacity: 1 }
          }
          className="w-full max-w-sm bg-white rounded-2xl overflow-hidden shadow-2xl cursor-grab select-none relative"
        >
          {/* --- Accept overlay (green, right) --- */}
          <motion.div
            style={{ opacity: acceptOpacity }}
            className="absolute inset-0 bg-emerald-500/90 flex items-center justify-center z-10 pointer-events-none rounded-2xl"
          >
            <div className="text-center">
              <span className="text-5xl mb-2 block">✅</span>
              <p className="text-white font-bold text-lg">确定替换</p>
            </div>
          </motion.div>

          {/* --- Skip overlay (red, left) --- */}
          <motion.div
            style={{ opacity: skipOpacity }}
            className="absolute inset-0 bg-rose-500/90 flex items-center justify-center z-10 pointer-events-none rounded-2xl"
          >
            <div className="text-center">
              <span className="text-5xl mb-2 block">🔄</span>
              <p className="text-white font-bold text-lg">换一个</p>
            </div>
          </motion.div>

          {/* --- Image Section --- */}
          <div className="relative h-52 overflow-hidden bg-slate-100">
            <img
              src={imageUrl}
              alt={candidate.name}
              className="w-full h-full object-cover"
              draggable={false}
              onError={(e) => {
                const target = e.currentTarget
                target.style.display = 'none'
                target.parentElement?.classList.add(
                  'bg-gradient-to-br',
                  candidateIdx % 3 === 0
                    ? 'from-amber-400 to-orange-500'
                    : candidateIdx % 3 === 1
                      ? 'from-emerald-400 to-teal-500'
                      : 'from-violet-400 to-purple-500',
                )
              }}
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />

            {/* Candidate index badge */}
            <div className="absolute top-3 left-3">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-white/90 backdrop-blur-sm text-slate-700 text-xs font-bold">
                替补 #{candidateIdx + 1}
              </span>
            </div>
          </div>

          {/* --- Content Section --- */}
          <div className="p-5 space-y-4">
            {/* Title */}
            <div>
              <h3 className="text-xl font-bold text-slate-900 leading-tight">
                {candidate.name}
              </h3>
              <p className="text-sm text-slate-400 mt-0.5 flex items-center gap-1">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                {candidate.address}
              </p>
            </div>

            {/* Info bar */}
            <div className="flex items-center gap-3 text-sm">
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-100">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                <span className="text-slate-600 font-medium">
                  {formatTime(candidate.start_time)} - {formatTime(candidate.end_time)}
                </span>
              </div>
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-400 text-xs">¥</span>
                <span className="text-slate-600 font-medium">
                  {candidate.per_capita === 0 ? '免费' : `${candidate.per_capita}`}
                </span>
              </div>
            </div>

            {/* Tags */}
            <div className="flex flex-wrap gap-1.5">
              {tags.map((tag, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-slate-100 text-slate-500 border border-slate-200"
                >
                  {tag}
                </span>
              ))}
            </div>

            {/* Description */}
            <p className="text-sm text-slate-500 leading-relaxed line-clamp-2">
              {description}
            </p>

            {/* Action hints */}
            <div className="flex justify-between items-center pt-2 border-t border-slate-100">
              <div className="flex items-center gap-1 text-xs text-slate-400">
                <span>👈</span>
                <span>左滑换一个</span>
              </div>
              <p className="text-xs text-slate-300">← 滑动选择 →</p>
              <div className="flex items-center gap-1 text-xs text-slate-400">
                <span>确定替换</span>
                <span>👉</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Buttons row */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="flex gap-3 mt-5 w-full max-w-sm"
        >
          <button
            onClick={onSkip}
            className="flex-1 flex items-center justify-center gap-1.5 px-4 py-3 rounded-xl
                       bg-white/10 border border-white/20 text-white font-medium text-sm
                       hover:bg-white/20 active:scale-95 transition-all duration-150 backdrop-blur-sm"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M19 12H5m7-7l-7 7 7 7" />
            </svg>
            换一个
          </button>
          <button
            onClick={onAccept}
            className="flex-1 flex items-center justify-center gap-1.5 px-4 py-3 rounded-xl
                       bg-emerald-500 text-white font-semibold text-sm
                       hover:bg-emerald-600 active:scale-95 transition-all duration-150 shadow-lg shadow-emerald-500/25"
          >
            确定替换
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 12h14m-7-7l7 7-7 7" />
            </svg>
          </button>
        </motion.div>

        {/* Cancel link */}
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.25 }}
          onClick={onCancel}
          className="mt-4 text-white/60 text-sm hover:text-white transition-colors"
        >
          取消，保留原方案
        </motion.button>
      </motion.div>
    </AnimatePresence>
  )
}

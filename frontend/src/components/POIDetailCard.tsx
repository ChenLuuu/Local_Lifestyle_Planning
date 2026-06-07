import { useRef } from 'react'
import { motion, useMotionValue, useTransform } from 'framer-motion'
import type { ItineraryNode } from '../types'

interface Props {
  node: ItineraryNode
  index: number
  onReplace: () => void
  onClose: () => void
  onConfirm?: () => void
}

const SWIPE_THRESHOLD = 100

function formatTime(timeStr: string) {
  return timeStr.slice(0, 5)
}

function getPlaceholderImage(node: ItineraryNode): string {
  if (node.image_url) return node.image_url
  const seed = encodeURIComponent(node.name + node.node_type)
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

export default function POIDetailCard({ node, index, onReplace, onClose, onConfirm }: Props) {
  const imageUrl = getPlaceholderImage(node)
  const description = node.description ?? DEFAULT_DESCRIPTIONS[node.node_type] ?? DEFAULT_DESCRIPTIONS.default
  const tags = node.tags ?? [node.node_type === 'restaurant' ? '口碑推荐' : '热门打卡', '精选推荐']

  // --- Swipe gesture state ---
  const x = useMotionValue(0)
  const rotate = useTransform(x, [-200, 0, 200], [-8, 0, 8])
  const replaceOpacity = useTransform(x, [-SWIPE_THRESHOLD, 0], [1, 0])
  const confirmOpacity = useTransform(x, [0, SWIPE_THRESHOLD], [0, 1])
  const exiting = useRef(false)

  const handleDragEnd = (_: unknown, info: { offset: { x: number } }) => {
    if (exiting.current) return
    if (info.offset.x > SWIPE_THRESHOLD) {
      exiting.current = true
      // Right swipe → confirm
      onConfirm?.()
    } else if (info.offset.x < -SWIPE_THRESHOLD) {
      exiting.current = true
      // Left swipe → replace
      onReplace()
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 30, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 350, damping: 28 }}
      style={{ x, rotate }}
      drag="x"
      dragConstraints={{ left: -250, right: 250 }}
      dragElastic={0.85}
      onDragEnd={handleDragEnd}
      whileDrag={{ cursor: 'grabbing' }}
      className="
        rounded-2xl overflow-hidden bg-white shadow-2xl border border-slate-100
        max-w-md mx-auto cursor-grab select-none relative
      "
    >
      {/* --- Left swipe overlay: Replace (orange) --- */}
      <motion.div
        style={{ opacity: replaceOpacity }}
        className="absolute inset-0 bg-gradient-to-r from-orange-500 via-orange-400 to-transparent flex items-center justify-start px-8 z-20 pointer-events-none rounded-2xl"
      >
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
              <path d="M1 4v6h6" />
              <path d="M3.51 15a9 9 0 102.13-9.36L1 10" />
            </svg>
          </div>
          <div>
            <p className="text-white font-bold text-lg">换一个</p>
            <p className="text-white/70 text-xs">左滑查看更多替补</p>
          </div>
        </div>
      </motion.div>

      {/* --- Right swipe overlay: Confirm (green) --- */}
      <motion.div
        style={{ opacity: confirmOpacity }}
        className="absolute inset-0 bg-gradient-to-l from-emerald-500 via-emerald-400 to-transparent flex items-center justify-end px-8 z-20 pointer-events-none rounded-2xl"
      >
        <div className="flex items-center gap-3">
          <div>
            <p className="text-white font-bold text-lg text-right">确认此站</p>
            <p className="text-white/70 text-xs text-right">右滑确认选择</p>
          </div>
          <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
        </div>
      </motion.div>

      {/* --- Cover Image Section --- */}
      <div className="relative h-44 overflow-hidden bg-slate-100">
        <img
          src={imageUrl}
          alt={node.name}
          className="w-full h-full object-cover"
          loading="lazy"
          draggable={false}
          onError={(e) => {
            const target = e.currentTarget
            target.style.display = 'none'
            const parent = target.parentElement
            if (parent) {
              parent.classList.add(
                'bg-gradient-to-br',
                index % 3 === 0
                  ? 'from-amber-400 to-orange-500'
                  : index % 3 === 1
                    ? 'from-emerald-400 to-teal-500'
                    : 'from-violet-400 to-purple-500',
              )
            }
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />

        {/* Node index badge */}
        <div className="absolute top-3 left-3">
          <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-white/90 backdrop-blur-sm text-slate-800 font-bold text-sm shadow-md">
            {index + 1}
          </span>
        </div>

        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/20 backdrop-blur-sm text-white flex items-center justify-center hover:bg-black/40 transition-colors"
          aria-label="关闭详情"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M1 1l12 12M13 1L1 13" />
          </svg>
        </button>
      </div>

      {/* --- Content Section --- */}
      <div className="p-5 space-y-4">
        {/* Title row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-bold text-slate-900 leading-tight truncate">
              {node.name}
            </h3>
            <p className="text-sm text-slate-400 mt-0.5 flex items-center gap-1">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
              <span className="truncate">{node.address}</span>
            </p>
          </div>

          {node.rating && (
            <div className="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-amber-50 border border-amber-100">
              <span className="text-amber-500 text-xs">★</span>
              <span className="text-sm font-bold text-amber-700">{node.rating}</span>
              {node.review_count && (
                <span className="text-[10px] text-amber-400">({node.review_count})</span>
              )}
            </div>
          )}
        </div>

        {/* Time and cost info bar */}
        <div className="flex items-center gap-3 text-sm">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-100">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            <span className="text-slate-600 font-medium">
              {formatTime(node.start_time)} - {formatTime(node.end_time)}
            </span>
            <span className="text-slate-400">({node.duration_min}分钟)</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-100">
            <span className="text-slate-400 text-xs">¥</span>
            <span className="text-slate-600 font-medium">
              {node.per_capita === 0 ? '免费' : `人均 ${node.per_capita}`}
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
        <p className="text-sm text-slate-500 leading-relaxed line-clamp-3">
          {description}
        </p>

        {/* Transit info to next */}
        {node.transit_to_next && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r from-slate-50 to-transparent border border-slate-100">
            <span className="text-sm">→</span>
            <span className="text-xs text-slate-500 font-medium">
              {node.transit_to_next.mode === '步行'
                ? '🚶 步行'
                : node.transit_to_next.mode === '共享单车'
                  ? '🚲 共享单车'
                  : node.transit_to_next.mode === '地铁'
                    ? '🚇 地铁'
                    : '🚗 打车'}
              {' · '}
              {node.transit_to_next.duration_min}分钟
              {' · '}
              {node.transit_to_next.distance_km}km
            </span>
          </div>
        )}

        {/* Swipe hint + Action buttons */}
        <div className="space-y-3 pt-1">
          {/* Swipe guide */}
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-1 text-[11px] text-slate-400">
              <span className="text-base">👈</span>
              <span>左滑换一个</span>
            </div>
            <span className="text-[10px] text-slate-300">← 滑动操作 →</span>
            <div className="flex items-center gap-1 text-[11px] text-slate-400">
              <span>确认此站</span>
              <span className="text-base">👉</span>
            </div>
          </div>

          {/* Explicit buttons as fallback */}
          <div className="flex gap-2">
            <button
              onClick={onReplace}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl
                         border-2 border-brand-orange text-brand-orange font-semibold text-sm
                         hover:bg-orange-50 active:scale-95 transition-all duration-150"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M1 4v6h6" />
                <path d="M3.51 15a9 9 0 102.13-9.36L1 10" />
              </svg>
              换一个
            </button>
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2.5 rounded-xl bg-slate-100 text-slate-600 font-medium text-sm
                         hover:bg-slate-200 active:scale-95 transition-all duration-150"
            >
              收起
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

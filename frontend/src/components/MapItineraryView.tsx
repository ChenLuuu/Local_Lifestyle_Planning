/**
 * MapItineraryView.tsx — 智能规划地图视图
 *
 * Z-Index 层级体系：
 *   Z=0   MapBackground   全屏地图底座（伪地图纹理背景）
 *   Z=10  RoutePath       SVG 动画虚线连接线
 *   Z=20  MapMarker       圆形序号标记点
 *   Z=30  POIDetailCard   地点概览卡片（点击标记弹出）
 *   Z=40  SwipeCard       替补方案滑卡（全屏遮罩 + Tinder 交互）
 *
 * 动效阈值设定：
 *   - Marker 点击: spring stiffness=400 damping=22, scale 1→1.25
 *   - 卡片出现: spring stiffness=350 damping=28, y+30→0+opacity
 *   - 滑卡拖拽: drag="x", 阈值 ±100px (左=换一个, 右=确定)
 *   - 卡片退出: easeOut 0.25s, x→±400 + opacity→0
 *   - 虚线动画: stroke-dashoffset, 2s linear infinite
 *   - 脉冲环: 2s easeInOut infinite, scale 1→1.8→1
 */

import { useState, useMemo, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ConstraintSet, Itinerary, ItineraryNode } from '../types'
import { fetchSwapCandidates, acceptSwap } from '../api'
import MapMarker from './MapMarker'
import POIDetailCard from './POIDetailCard'
import SwipeReplacementCard from './SwipeReplacementCard'

interface Props {
  sessionId: string
  itinerary: Itinerary
  constraintSet: ConstraintSet
  onDone: (itinerary: Itinerary) => void
  onBack: () => void
}

// ---- Position calculation: distributed along a curvy route ----
interface MarkerPosition {
  xPct: number
  yPct: number
}

function calcMarkerPositions(count: number): MarkerPosition[] {
  if (count <= 0) return []
  if (count === 1) return [{ xPct: 50, yPct: 45 }]

  const positions: MarkerPosition[] = []
  for (let i = 0; i < count; i++) {
    const t = i / (count - 1)
    // x: evenly spaced from 18% to 82%
    const xPct = 18 + t * 64
    // y: sinusoidal curve, oscillating around center
    const yPct = 42 + Math.sin(t * Math.PI) * 28
    positions.push({ xPct, yPct })
  }
  return positions
}

// ---- SVG Route path generator ----
function buildSVGPath(positions: MarkerPosition[]): string {
  if (positions.length < 2) return ''
  const pts = positions.map((p) => ({ x: p.xPct, y: p.yPct }))

  // Build a smooth curved path using cubic beziers
  let d = `M ${pts[0].x} ${pts[0].y}`
  for (let i = 1; i < pts.length; i++) {
    const prev = pts[i - 1]
    const curr = pts[i]
    const midX = (prev.x + curr.x) / 2
    d += ` C ${midX} ${prev.y}, ${midX} ${curr.y}, ${curr.x} ${curr.y}`
  }
  return d
}

// ---- Sub-component: Animated Map Background ----
function MapBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden" style={{ zIndex: 0 }}>
      {/* Base color layer */}
      <div className="absolute inset-0 bg-gradient-to-br from-stone-50 via-slate-50 to-amber-50/40" />

      {/* City grid pattern */}
      <svg
        className="absolute inset-0 w-full h-full opacity-[0.06]"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern id="city-grid" width="80" height="80" patternUnits="userSpaceOnUse">
            <path
              d="M 80 0 L 0 0 0 80"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.5"
              className="text-slate-400"
            />
          </pattern>
          <pattern id="city-grid-large" width="240" height="240" patternUnits="userSpaceOnUse">
            <rect width="240" height="240" fill="url(#city-grid)" />
            <path
              d="M 240 0 L 0 0 0 240"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-slate-500"
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#city-grid-large)" />
      </svg>

      {/* Abstract road curves */}
      <svg
        className="absolute inset-0 w-full h-full opacity-[0.08]"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <path
          d="M 5 30 Q 25 20, 45 45 T 85 35"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="text-amber-600"
        />
        <path
          d="M 10 70 Q 30 55, 50 60 T 90 50"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-slate-600"
        />
        <path
          d="M 15 90 Q 40 80, 55 85"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
          className="text-slate-500"
        />
      </svg>

      {/* Decorative park-like green patches */}
      <div className="absolute top-[15%] right-[12%] w-24 h-24 rounded-[40%] bg-emerald-200/25 blur-xl" />
      <div className="absolute bottom-[25%] left-[10%] w-20 h-20 rounded-[45%] bg-emerald-200/20 blur-xl" />
      <div className="absolute top-[45%] left-[55%] w-16 h-16 rounded-[35%] bg-amber-200/20 blur-lg" />

      {/* Water-like blue area */}
      <div className="absolute bottom-[8%] right-[5%] w-32 h-16 rounded-[50%] bg-blue-200/15 blur-xl" />
    </div>
  )
}

// ---- Sub-component: Animated Route Lines ----
function RouteLines({ positions }: { positions: MarkerPosition[] }) {
  if (positions.length < 2) return null
  const d = buildSVGPath(positions)

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ zIndex: 10 }}
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      {/* Shadow/glow layer */}
      <path
        d={d}
        fill="none"
        stroke="rgba(255,96,0,0.12)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Main dashed path */}
      <path
        d={d}
        fill="none"
        stroke="url(#route-dash-gradient)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray="6 4"
        className="route-dash-animated"
      />

      <defs>
        <linearGradient id="route-dash-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#FF6000" stopOpacity="0.9" />
          <stop offset="50%" stopColor="#FF8A33" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#FF6000" stopOpacity="0.9" />
        </linearGradient>
      </defs>

      {/* Start dot */}
      <circle
        cx={positions[0].xPct}
        cy={positions[0].yPct}
        r="1.8"
        fill="#FF6000"
        opacity="0.6"
      />

      {/* End pin */}
      <circle
        cx={positions[positions.length - 1].xPct}
        cy={positions[positions.length - 1].yPct}
        r="2.2"
        fill="none"
        stroke="#FF6000"
        strokeWidth="1.5"
        opacity="0.5"
      />
    </svg>
  )
}

// ---- Sub-component: Fault Notice Banner ----
function FaultNotice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -30 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="absolute top-4 left-4 right-4 z-50 max-w-md mx-auto"
    >
      <div className="rounded-xl bg-amber-50/95 backdrop-blur-sm border border-amber-200 p-3.5 flex items-start gap-3 shadow-lg">
        <span className="text-amber-500 text-base shrink-0 mt-0.5">⚠️</span>
        <p className="text-sm text-amber-700 flex-1 leading-relaxed">{message}</p>
        <button
          onClick={onDismiss}
          className="text-amber-400 hover:text-amber-600 shrink-0 transition-colors"
          aria-label="关闭"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      </div>
    </motion.div>
  )
}

// ---- Sub-component: Bottom Control Bar ----
function BottomBar({
  confirmedCount,
  totalCount,
  allConfirmed,
  onDone,
  onBack,
}: {
  confirmedCount: number
  totalCount: number
  allConfirmed: boolean
  onDone: () => void
  onBack: () => void
}) {
  return (
    <motion.div
      initial={{ y: 80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ delay: 0.2, type: 'spring', stiffness: 300, damping: 25 }}
      className="absolute bottom-0 left-0 right-0 z-35 px-4 pb-6 pt-3"
    >
      <div className="max-w-md mx-auto">
        {/* Glass-morphism container */}
        <div className="bg-white/85 backdrop-blur-xl rounded-2xl shadow-2xl border border-slate-200/60 p-4 space-y-3">
          {/* Progress summary */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex -space-x-1">
                {Array.from({ length: totalCount }).map((_, i) => (
                  <div
                    key={i}
                    className={`w-7 h-7 rounded-full border-2 border-white flex items-center justify-center text-[11px] font-bold shadow-sm transition-colors ${
                      i < confirmedCount
                        ? 'bg-emerald-500 text-white'
                        : 'bg-slate-200 text-slate-400'
                    }`}
                  >
                    {i < confirmedCount ? '✓' : i + 1}
                  </div>
                ))}
              </div>
              <span className="text-xs text-slate-500 font-medium ml-2">
                {confirmedCount}/{totalCount} 已确认
              </span>
            </div>
            <span className="text-xs text-slate-400">点击标记查看详情</span>
          </div>

          {/* Action buttons */}
          <div className="flex gap-2">
            <button onClick={onBack} className="btn-secondary flex-1 text-sm !py-2.5">
              ← 重新规划
            </button>
            <button
              onClick={onDone}
              disabled={!allConfirmed}
              className="btn-primary flex-1 text-sm !py-2.5"
            >
              {allConfirmed ? '确认方案，进入协同 →' : `还有 ${totalCount - confirmedCount} 个节点未确认`}
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

// ---- Main Component ----
export default function MapItineraryView({
  sessionId,
  itinerary: initialItinerary,
  constraintSet,
  onDone,
  onBack,
}: Props) {
  // --- State ---
  const [itinerary, setItinerary] = useState(initialItinerary)
  const [selectedNodeIdx, setSelectedNodeIdx] = useState<number | null>(null)
  const [confirmedNodes, setConfirmedNodes] = useState<Set<number>>(new Set())
  const [faultNotice, setFaultNotice] = useState<string | null>(null)

  // Swap state
  const [swap, setSwap] = useState<{
    nodeIndex: number
    candidates: ItineraryNode[]
    candidateIdx: number
    loading: boolean
  } | null>(null)

  // --- Derived ---
  const positions = useMemo(() => calcMarkerPositions(itinerary.nodes.length), [itinerary.nodes.length])
  const nodes = itinerary.nodes
  const allConfirmed = confirmedNodes.size >= nodes.length

  // --- Handlers ---
  const handleMarkerClick = useCallback((idx: number) => {
    setSelectedNodeIdx((prev) => (prev === idx ? null : idx))
    setFaultNotice(null)
  }, [])

  const handleReplaceRequest = useCallback(
    async (nodeIndex: number) => {
      setSelectedNodeIdx(null)
      setSwap({ nodeIndex, candidates: [], candidateIdx: 0, loading: true })

      try {
        const candidates = await fetchSwapCandidates(sessionId, itinerary, nodeIndex, constraintSet)
        setSwap({ nodeIndex, candidates, candidateIdx: 0, loading: false })
      } catch {
        setFaultNotice('获取替补方案失败，请重试')
        setSwap(null)
      }
    },
    [sessionId, itinerary, constraintSet],
  )

  const handleSwapAccept = useCallback(async () => {
    if (!swap || swap.candidates.length === 0) return
    const candidate = swap.candidates[swap.candidateIdx]

    try {
      const newItinerary = await acceptSwap(sessionId, itinerary, swap.nodeIndex, candidate, constraintSet)
      setItinerary(newItinerary)
      setConfirmedNodes((prev) => {
        const next = new Set(prev)
        next.add(swap.nodeIndex)
        return next
      })
      setFaultNotice(`✅ 已替换为「${candidate.name}」，时间线已重算`)
      setSwap(null)
    } catch {
      setFaultNotice('替换失败，请重试')
    }
  }, [swap, sessionId, itinerary, constraintSet])

  const handleSwapSkip = useCallback(() => {
    if (!swap) return
    if (swap.candidateIdx < swap.candidates.length - 1) {
      setSwap((s) => (s ? { ...s, candidateIdx: s.candidateIdx + 1 } : null))
    } else {
      setFaultNotice('已无更多替补，保留原方案')
      setSwap(null)
    }
  }, [swap])

  const handleSwapCancel = useCallback(() => {
    setSwap(null)
  }, [])

  const handleMarkerConfirm = useCallback(
    (idx: number) => {
      setConfirmedNodes((prev) => {
        const next = new Set(prev)
        next.add(idx)
        return next
      })
      setSelectedNodeIdx(null)
      setFaultNotice(`✅ 第 ${idx + 1} 站「${nodes[idx].name}」已确认`)
    },
    [nodes],
  )

  // --- Render ---
  return (
    <div className="fixed inset-0 select-none" style={{ overflow: 'hidden' }}>
      {/* ========== Z=0: Map Background ========== */}
      <MapBackground />

      {/* ========== Z=10: Route Lines ========== */}
      <RouteLines positions={positions} />

      {/* ========== Z=20: Map Markers ========== */}
      {nodes.map((node, i) => {
        const pos = positions[i]
        if (!pos) return null

        return (
          <div
            key={node.node_id}
            className="absolute"
            style={{
              left: `${pos.xPct}%`,
              top: `${pos.yPct}%`,
            }}
          >
            <MapMarker
              node={node}
              index={i}
              isSelected={selectedNodeIdx === i}
              isConfirmed={confirmedNodes.has(i)}
              onClick={() => handleMarkerClick(i)}
            />
          </div>
        )
      })}

      {/* ========== Z=30: POI Detail Card ========== */}
      <AnimatePresence>
        {selectedNodeIdx !== null && (
          <div
            className="absolute left-0 right-0 flex justify-center pointer-events-none"
            style={{
              // Position card in the upper-middle area for immediate visibility
              top: '8%',
              zIndex: 30,
            }}
          >
            {/* Pointer-events wrapper so card itself is interactive */}
            <div className="w-full max-w-md pointer-events-auto">
              <POIDetailCard
                node={nodes[selectedNodeIdx]}
                index={selectedNodeIdx}
                onReplace={() => handleReplaceRequest(selectedNodeIdx)}
                onClose={() => setSelectedNodeIdx(null)}
                onConfirm={() => handleMarkerConfirm(selectedNodeIdx)}
              />
            </div>
          </div>
        )}
      </AnimatePresence>

      {/* ========== Z=40: Swipe Replacement Card ========== */}
      <AnimatePresence>
        {swap && !swap.loading && swap.candidates.length > 0 && (
          <SwipeReplacementCard
            candidate={swap.candidates[swap.candidateIdx]}
            originalName={nodes[swap.nodeIndex].name}
            candidateIdx={swap.candidateIdx}
            totalCandidates={swap.candidates.length}
            onAccept={handleSwapAccept}
            onSkip={handleSwapSkip}
            onCancel={handleSwapCancel}
          />
        )}

        {/* Loading state for swap */}
        {swap && swap.loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 flex items-center justify-center"
            onClick={handleSwapCancel}
          >
            <div className="bg-white rounded-2xl p-8 shadow-2xl text-center space-y-4">
              <div className="flex justify-center gap-2">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-3 h-3 rounded-full bg-brand-orange"
                    animate={{ scale: [1, 1.4, 1], opacity: [1, 0.5, 1] }}
                    transition={{
                      duration: 1.2,
                      repeat: Infinity,
                      delay: i * 0.2,
                      ease: 'easeInOut',
                    }}
                  />
                ))}
              </div>
              <p className="text-slate-500 text-sm">正在搜索替补方案…</p>
            </div>
          </motion.div>
        )}

        {/* No candidates state */}
        {swap && !swap.loading && swap.candidates.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 flex items-center justify-center"
            onClick={handleSwapCancel}
          >
            <div className="bg-white rounded-2xl p-8 shadow-2xl text-center space-y-3">
              <span className="text-4xl">😔</span>
              <p className="text-slate-600 font-medium">暂无替补方案</p>
              <p className="text-slate-400 text-sm">当前区域暂无其他合适的地点</p>
              <button
                onClick={handleSwapCancel}
                className="mt-2 px-6 py-2 rounded-xl bg-slate-100 text-slate-600 text-sm font-medium hover:bg-slate-200 transition-colors"
              >
                保留原方案
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ========== Z=50: Fault Notice ========== */}
      <AnimatePresence>
        {faultNotice && (
          <FaultNotice message={faultNotice} onDismiss={() => setFaultNotice(null)} />
        )}
      </AnimatePresence>

      {/* ========== Z=35: Bottom Control Bar ========== */}
      <BottomBar
        confirmedCount={confirmedNodes.size}
        totalCount={nodes.length}
        allConfirmed={allConfirmed}
        onDone={() => onDone(itinerary)}
        onBack={onBack}
      />

      {/* CSS animation for route dash flow */}
      <style>{`
        @keyframes routeDashFlow {
          from { stroke-dashoffset: 0; }
          to   { stroke-dashoffset: -20; }
        }
        .route-dash-animated {
          animation: routeDashFlow 2s linear infinite;
        }
      `}</style>
    </div>
  )
}

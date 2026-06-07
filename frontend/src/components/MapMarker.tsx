import { motion } from 'framer-motion'
import type { ItineraryNode } from '../types'

const NODE_TYPE_ICON: Record<string, string> = {
  restaurant: '🍽️',
  venue: '🎯',
  activity: '🎪',
  transport: '🚗',
  shopping: '🛍️',
  default: '📍',
}

interface Props {
  node: ItineraryNode
  index: number
  isSelected: boolean
  isConfirmed: boolean
  onClick: () => void
}

const markerSpring = {
  type: 'spring',
  stiffness: 400,
  damping: 22,
}

export default function MapMarker({ node, index, isSelected, isConfirmed, onClick }: Props) {
  const icon = NODE_TYPE_ICON[node.node_type] ?? NODE_TYPE_ICON.default

  return (
    <button
      onClick={onClick}
      className="absolute group cursor-pointer"
      style={{
        transform: 'translate(-50%, -50%)',
        zIndex: isSelected ? 25 : 20,
      }}
      aria-label={`${node.name} - 第 ${index + 1} 站`}
    >
      {/* Pulsing ring when selected */}
      {isSelected && (
        <motion.div
          className="absolute inset-0 rounded-full bg-brand-orange/20"
          initial={{ scale: 1, opacity: 0.6 }}
          animate={{
            scale: [1, 1.8, 1],
            opacity: [0.4, 0, 0.4],
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
          style={{ left: -8, right: -8, top: -8, bottom: -8 }}
        />
      )}

      {/* Main marker circle */}
      <motion.div
        animate={{
          scale: isSelected ? 1.25 : 1,
          boxShadow: isSelected
            ? '0 0 0 4px rgba(255,96,0,0.3), 0 4px 14px rgba(255,96,0,0.35)'
            : '0 2px 8px rgba(0,0,0,0.15)',
        }}
        transition={markerSpring}
        className={`
          w-11 h-11 rounded-full flex items-center justify-center
          text-white font-bold text-sm
          border-[3px] border-white
          transition-colors duration-200
          ${isConfirmed
            ? 'bg-emerald-500 shadow-emerald-200'
            : isSelected
              ? 'bg-brand-orange shadow-orange-300'
              : 'bg-slate-700 shadow-slate-300 hover:bg-brand-orange'
          }
        `}
      >
        {isConfirmed ? (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 500, damping: 15 }}
            className="text-base"
          >
            ✓
          </motion.span>
        ) : (
          <span>{index + 1}</span>
        )}
      </motion.div>

      {/* Label below marker */}
      <motion.div
        animate={{ opacity: isSelected ? 1 : 0.85, y: isSelected ? 4 : 0 }}
        className="mt-2 text-center pointer-events-none"
      >
        <span
          className={`
            inline-block px-2.5 py-1 rounded-full text-[11px] font-semibold
            whitespace-nowrap shadow-sm
            ${isSelected
              ? 'bg-brand-orange text-white'
              : 'bg-white/90 text-slate-700 backdrop-blur-sm'
            }
          `}
        >
          {icon} {node.name.length > 6 ? node.name.slice(0, 6) + '…' : node.name}
        </span>
      </motion.div>
    </button>
  )
}

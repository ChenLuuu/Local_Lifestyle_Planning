import { motion } from 'framer-motion'

interface Props {
  confirmationText: string
  learningLog: string[]
  onRestart: () => void
}

export default function DonePage({ confirmationText, learningLog, onRestart }: Props) {
  return (
    <div className="space-y-4">
      {/* Success hero */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="card text-center py-8 bg-gradient-to-b from-green-50 to-white border-green-100"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
          className="text-6xl mb-4"
        >
          🎉
        </motion.div>
        <h2 className="text-2xl font-bold text-gray-800 mb-2">行程确认！</h2>
        <p className="text-sm text-gray-500 leading-relaxed max-w-xs mx-auto">
          {confirmationText || '所有预订已完成，祝你玩得开心！'}
        </p>
      </motion.div>

      {/* Learning Log — F09 飞轮可见性 */}
      {learningLog.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">🧠</span>
            <div>
              <h3 className="font-semibold text-gray-800 text-sm">Learning Log</h3>
              <p className="text-xs text-gray-400">本次规划让我更了解你</p>
            </div>
          </div>
          <div className="space-y-2">
            {learningLog.map((log, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 + i * 0.1 }}
                className="flex items-start gap-2 bg-blue-50 rounded-xl px-3 py-2"
              >
                <p className="text-xs text-blue-600 leading-relaxed">{log}</p>
              </motion.div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100">
            <p className="text-xs text-gray-400">
              下次规划同类场景时，这些偏好将自动生效，减少你的决策负担 ↗
            </p>
          </div>
        </motion.div>
      )}

      {/* Stats */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="grid grid-cols-3 gap-3"
      >
        {[
          { label: '已规划', value: '1 次' },
          { label: '偏好学习', value: `${learningLog.length} 条` },
          { label: '下次更精准', value: '✓' },
        ].map(stat => (
          <div key={stat.label} className="card text-center py-4">
            <p className="text-lg font-bold text-brand-orange">{stat.value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{stat.label}</p>
          </div>
        ))}
      </motion.div>

      {/* Actions */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
        className="space-y-2"
      >
        <button className="btn-primary w-full" onClick={onRestart}>
          ＋ 再规划一次
        </button>
        <p className="text-xs text-center text-gray-400">
          本次偏好已写入用户画像，下次规划将更懂你
        </p>
      </motion.div>
    </div>
  )
}

import { useState } from 'react'
import { motion } from 'framer-motion'
import { loginUser } from '../api'
import type { UserProfile } from '../types'

interface Props {
  onDone: (profile: UserProfile) => void
}

export default function LoginPage({ onDone }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleLogin = async () => {
    setLoading(true)
    setError('')
    try {
      const profile = await loginUser()
      onDone(profile)
    } catch {
      setError('登录失败，请重试')
      setLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="flex flex-col items-center gap-6 pt-8"
    >
      {/* Hero card */}
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className="w-full rounded-3xl p-8 text-center relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #FF6200 0%, #D94A00 100%)' }}
      >
        <div className="absolute top-0 right-0 w-40 h-40 bg-white/10 rounded-full -translate-y-1/2 translate-x-1/4" />
        <div className="absolute bottom-0 left-0 w-28 h-28 bg-white/10 rounded-full translate-y-1/2 -translate-x-1/4" />

        <motion.div
          initial={{ scale: 0, rotate: -10 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 200, delay: 0.2 }}
          className="text-7xl mb-4 relative"
        >
          🐻
        </motion.div>

        <h1 className="text-2xl font-bold text-white relative">欢迎回来，小团</h1>
        <p className="text-sm text-white/80 mt-2 relative">你的专属出行规划助手已就位</p>
      </motion.div>

      {/* Feature highlights */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="w-full space-y-3"
      >
        {[
          { icon: '🧠', title: '记住你的喜好', desc: '每次出行后自动学习你的偏好，越用越懂你' },
          { icon: '✨', title: 'AI 智能分析', desc: '输入特别需求，AI 自动提取你的个性标签' },
          { icon: '🚀', title: '规划更精准', desc: '下次规划直接融入你的历史偏好数据' },
        ].map((item, i) => (
          <motion.div
            key={item.title}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.35 + i * 0.08 }}
            className="flex items-start gap-3 bg-white rounded-2xl p-4 shadow-sm border border-orange-50"
          >
            <span className="text-2xl mt-0.5">{item.icon}</span>
            <div>
              <p className="font-semibold text-gray-800 text-sm">{item.title}</p>
              <p className="text-xs text-gray-500 mt-0.5">{item.desc}</p>
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* Error */}
      {error && (
        <p className="text-red-500 text-sm">{error}</p>
      )}

      {/* CTA */}
      <motion.button
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.55 }}
        whileTap={{ scale: 0.97 }}
        className="w-full btn-primary text-base py-4"
        onClick={handleLogin}
        disabled={loading}
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            正在登录…
          </span>
        ) : (
          '🐻 以小团身份开始规划'
        )}
      </motion.button>

      <p className="text-xs text-gray-400 text-center">演示模式 · 固定账号 · 无需密码</p>
    </motion.div>
  )
}

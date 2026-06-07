/**
 * ItineraryPage.tsx — 「方案确认」阶段入口页
 *
 * v2.0: 集成 MapItineraryView，替换原有的纯文字时间线卡片 UI。
 * 现在使用「全屏地图底座 + 悬浮富媒体卡片」的交互范式。
 * 保持与 App.tsx 的 Props 接口完全兼容。
 */

import type { ConstraintSet, Itinerary } from '../types'
import MapItineraryView from './MapItineraryView'

interface Props {
  sessionId: string
  itinerary: Itinerary
  constraintSet: ConstraintSet
  onDone: (itinerary: Itinerary) => void
  onBack: () => void
}

export default function ItineraryPage(props: Props) {
  return <MapItineraryView {...props} />
}

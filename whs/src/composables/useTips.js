import { reactive } from 'vue'

// 模块级单例：所有组件共享同一份通知队列
const state = reactive({ tips: [] })
let seq = 0
const DEFAULT_DURATION = 3000
const LEAVE_MS = 300 // 离开动画时长，期间标记 leaving，动画结束后才真正移除

export function useTips() {
  function dismiss(id) {
    const tip = state.tips.find((t) => t.id === id)
    if (!tip || tip.leaving) return
    // 先标记 leaving 播放离开动画，动画结束后再移除
    tip.leaving = true
    setTimeout(() => {
      const index = state.tips.findIndex((t) => t.id === id)
      if (index !== -1) state.tips.splice(index, 1)
    }, LEAVE_MS)
  }

  // type: 'info' | 'warning' | 'error'；content: 展示文本；duration: 自动消失毫秒数
  function showTip(type, content, duration = DEFAULT_DURATION) {
    const normalized = ['info', 'warning', 'error'].includes(type) ? type : 'info'
    const id = ++seq
    state.tips.push({ id, type: normalized, content: String(content ?? ''), leaving: false })
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration)
    }
    return id
  }

  return { state, showTip, dismiss }
}

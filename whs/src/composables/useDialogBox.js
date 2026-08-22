/**
 * 对话框组合式函数（替代 window.confirm / window.alert）。
 *
 * 模块级单例：所有组件共享同一份对话框状态，配合全局挂载的
 * dialog_box.vue 渲染。调用方以 Promise 方式等待用户选择。
 *
 * 用法：
 *   const dialogBox = useDialogBox()
 *   const ok = await dialogBox.confirm({ title, message, confirmText?, cancelText?, danger? })
 *   await dialogBox.alert({ title, message })
 */
import { reactive } from 'vue'

const state = reactive({
  visible: false,
  type: 'confirm', // 'confirm' | 'alert'
  title: '',
  message: '',
  confirmText: '',
  cancelText: '',
  danger: false,
})

let resolver = null

export function useDialogBox() {
  function open(options, type) {
    state.type = type
    state.title = String(options.title ?? '')
    state.message = String(options.message ?? '')
    state.confirmText = String(options.confirmText ?? '')
    state.cancelText = String(options.cancelText ?? '')
    state.danger = !!options.danger
    state.visible = true
    return new Promise((resolve) => {
      resolver = resolve
    })
  }

  // 确认框：resolve(true) / resolve(false)
  function confirm(options = {}) {
    return open(options, 'confirm')
  }

  // 提示框：仅"确定"，resolve(false)（调用方无需关心结果）
  function alert(options = {}) {
    return open(options, 'alert')
  }

  // 关闭对话框并交付结果
  function close(result = false) {
    state.visible = false
    const r = resolver
    resolver = null
    if (r) r(result)
  }

  return { state, confirm, alert, close }
}

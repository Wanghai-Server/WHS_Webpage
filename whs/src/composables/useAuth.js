import { reactive } from 'vue'
import i18n from '../i18n'
import { useTips } from './useTips'

// 模块级单例：所有组件共享同一份登录态
const state = reactive({
  token: localStorage.getItem('token') || '',
  user: JSON.parse(localStorage.getItem('user') || 'null'),
})

// 并行 fetchMe 合并：同一时刻只发一个 /api/user/me 请求。
// 避免多个组件（如首页 + 导航栏）同时挂载时重复请求，以及封禁/锁定
// 提示被重复弹出；请求结束后重置，下次调用会重新发起。
let mePromise = null

// 后端错误消息结构 {zh, en}，按当前界面语言取一条
function localMessage(data) {
  const m = data && data.message
  if (!m) return ''
  const loc = i18n.global.locale.value
  return m[loc] || m.zh || m.en || ''
}

export function useAuth() {
  function setAuth(token, user) {
    state.token = token
    state.user = user
    localStorage.setItem('token', token)
    if (user) {
      localStorage.setItem('user', JSON.stringify(user))
    }
  }

  function updateUser(user) {
    state.user = user
    localStorage.setItem('user', JSON.stringify(user))
  }

  function clearAuth() {
    state.token = ''
    state.user = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  function isLoggedIn() {
    return !!state.token
  }

  // 用 token 向后端拉取最新用户信息（登录后刷新头像等）
  async function fetchMe() {
    if (!state.token) return null
    if (!mePromise) {
      mePromise = (async () => {
        try {
          const res = await fetch('/api/user/me', {
            headers: { Authorization: `Bearer ${state.token}` },
          })
          if (!res.ok) {
            // 账号被封禁 / 锁定：后端返回 403 + 错误码，统一用 tips 提示后登出
            const data = await res.json().catch(() => ({}))
            if (
              res.status === 403 &&
              (data.code === 'account_banned' || data.code === 'account_locked')
            ) {
              const { showTip } = useTips()
              showTip('error', localMessage(data) || i18n.global.t('auth.request_failed'))
            }
            clearAuth()
            return null
          }
          const user = await res.json()
          updateUser(user)
          return user
        } catch {
          return null
        } finally {
          mePromise = null
        }
      })()
    }
    return mePromise
  }

  return { state, setAuth, updateUser, clearAuth, isLoggedIn, fetchMe }
}

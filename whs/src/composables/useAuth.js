import { reactive } from 'vue'

// 模块级单例：所有组件共享同一份登录态
const state = reactive({
  token: localStorage.getItem('token') || '',
  user: JSON.parse(localStorage.getItem('user') || 'null'),
})

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
    try {
      const res = await fetch('/api/user/me', {
        headers: { Authorization: `Bearer ${state.token}` },
      })
      if (!res.ok) {
        clearAuth()
        return null
      }
      const user = await res.json()
      updateUser(user)
      return user
    } catch {
      return null
    }
  }

  return { state, setAuth, updateUser, clearAuth, isLoggedIn, fetchMe }
}

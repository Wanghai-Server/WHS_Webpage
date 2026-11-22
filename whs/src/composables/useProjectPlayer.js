/**
 * 工程功能：记住用户上次选择的 MC 账号。
 *
 * 仅保存在浏览器本地（localStorage），不写入服务器；账号列表变化或失效时回退主账号。
 */
const STORAGE_KEY = 'whs_project_player'

/** 返回应默认选中的玩家名：本地记忆（仍在账号列表内）→ 主账号 → 第一个账号。 */
export function preferredPlayer(accounts, fallback = '') {
  const names = (accounts || []).map((account) => account.name)
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved && names.includes(saved)) return saved
  return fallback || names[0] || ''
}

/** 记住当前选择的玩家名（"下次保持当前选择"按钮）。 */
export function rememberPlayer(name) {
  if (name) localStorage.setItem(STORAGE_KEY, name)
}

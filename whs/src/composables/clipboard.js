// 复制文本到剪贴板。优先使用异步 Clipboard API（仅安全上下文可用），
// 失败时回退到隐藏 textarea + execCommand，兼容非 HTTPS 环境。
export async function copyText(text) {
  const value = String(text)
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // 继续尝试回退方案
    }
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = value
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.top = '-9999px'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    ta.setSelectionRange(0, value.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

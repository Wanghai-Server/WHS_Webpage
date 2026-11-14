/**
 * MC 风格 § 颜色 / 格式代码插件（全站 Markdown 通用）。
 *
 * 背景：全站 markdown-it 均为 `html: false`（防止存储型 XSS），因此不能直接写
 * HTML/CSS。这里用自研 core rule 在 token 流层面解析 § 代码并输出**受控的**
 * `<span class="md-mc-color" style="...">`，不开启 HTML、不引入第三方依赖。
 *
 * 语法（仅普通文本生效；代码块 / 行内代码内原样显示）：
 * - 颜色：`§0`–`§f`（MC 官方 16 色） + `§#RRGGBB`（任意 HEX，扩展语法）
 * - 格式：`§l` 粗体、`§o` 斜体、`§n` 下划线、`§m` 删除线
 * - 复位：`§r`（同时清除颜色与格式）
 *
 * 与 MC 一致：颜色代码会重置当前格式；格式代码叠加生效；状态持续到本段结束。
 * 输出为逐段包裹的 span（不跨 token），避免与 `**bold**`、链接等标签交叉嵌套。
 */

export const MC_COLORS = [
  { code: '0', hex: '#000000', name: 'black' },
  { code: '1', hex: '#0000AA', name: 'dark_blue' },
  { code: '2', hex: '#00AA00', name: 'dark_green' },
  { code: '3', hex: '#00AAAA', name: 'dark_aqua' },
  { code: '4', hex: '#AA0000', name: 'dark_red' },
  { code: '5', hex: '#AA00AA', name: 'dark_purple' },
  { code: '6', hex: '#FFAA00', name: 'gold' },
  { code: '7', hex: '#AAAAAA', name: 'gray' },
  { code: '8', hex: '#555555', name: 'dark_gray' },
  { code: '9', hex: '#5555FF', name: 'blue' },
  { code: 'a', hex: '#55FF55', name: 'green' },
  { code: 'b', hex: '#55FFFF', name: 'aqua' },
  { code: 'c', hex: '#FF5555', name: 'red' },
  { code: 'd', hex: '#FF55FF', name: 'light_purple' },
  { code: 'e', hex: '#FFFF55', name: 'yellow' },
  { code: 'f', hex: '#FFFFFF', name: 'white' },
]

const COLOR_MAP = new Map(MC_COLORS.map((c) => [c.code, c.hex]))
const FORMAT_CODES = new Set(['l', 'o', 'n', 'm'])
const HEX_RE = /^[0-9a-fA-F]{6}$/

function newState() {
  return { color: null, bold: false, italic: false, underline: false, strike: false }
}

function resetState(state) {
  state.color = null
  state.bold = false
  state.italic = false
  state.underline = false
  state.strike = false
}

// 颜色代码会清除格式（与 MC 语义一致）
function resetFormats(state) {
  state.bold = false
  state.italic = false
  state.underline = false
  state.strike = false
}

function applyFormat(state, code) {
  if (code === 'l') state.bold = true
  else if (code === 'o') state.italic = true
  else if (code === 'n') state.underline = true
  else if (code === 'm') state.strike = true
}

function styleOf(state) {
  const parts = []
  if (state.color) parts.push(`color:${state.color}`)
  if (state.bold) parts.push('font-weight:700')
  if (state.italic) parts.push('font-style:italic')
  const decorations = []
  if (state.underline) decorations.push('underline')
  if (state.strike) decorations.push('line-through')
  if (decorations.length) parts.push(`text-decoration:${decorations.join(' ')}`)
  return parts.join(';')
}

/**
 * 重写一段 inline token 的子 token：把 § 代码从文本中剥离，
 * 并按当前样式把文本片段包成受控 span。
 */
function rewriteChildren(state, children) {
  const st = newState()
  const out = []

  const pushText = (content) => {
    if (!content) return
    const token = new state.Token('text', '', 0)
    token.content = content
    out.push(token)
  }

  const flush = (buffer) => {
    if (!buffer) return
    const style = styleOf(st)
    if (!style) {
      pushText(buffer)
      return
    }
    const open = new state.Token('html_inline', '', 0)
    open.content = `<span class="md-mc-color" style="${style}">`
    const close = new state.Token('html_inline', '', 0)
    close.content = '</span>'
    out.push(open)
    pushText(buffer)
    out.push(close)
  }

  const walk = (children) => {
    for (const child of children) {
      if (child.type !== 'text') {
        out.push(child)
        continue
      }
      const content = child.content || ''
      let buffer = ''
      let i = 0
      while (i < content.length) {
        const ch = content[i]
        if (ch !== '§') {
          buffer += ch
          i += 1
          continue
        }
        const next = content[i + 1]
        // §#RRGGBB（扩展 HEX）
        if (next === '#') {
          const hex = content.slice(i + 2, i + 8)
          if (hex.length === 6 && HEX_RE.test(hex)) {
            flush(buffer)
            buffer = ''
            st.color = `#${hex.toLowerCase()}`
            resetFormats(st)
            i += 8
            continue
          }
        }
        const code = next ? next.toLowerCase() : ''
        if (next && COLOR_MAP.has(code)) {
          flush(buffer)
          buffer = ''
          st.color = COLOR_MAP.get(code)
          resetFormats(st)
          i += 2
          continue
        }
        if (next && (code === 'r' || code === 'R')) {
          flush(buffer)
          buffer = ''
          resetState(st)
          i += 2
          continue
        }
        if (next && FORMAT_CODES.has(code)) {
          flush(buffer)
          buffer = ''
          applyFormat(st, code)
          i += 2
          continue
        }
        // 非法 / 无关的 §：原样保留
        buffer += ch
        i += 1
      }
      flush(buffer)
    }
  }

  walk(children)
  return out
}

/**
 * markdown-it 插件：注册 § 颜色 / 格式代码解析。
 * @param {import('markdown-it')} md markdown-it 实例
 */
export function colorCodesPlugin(md) {
  md.core.ruler.push('whs_mc_color_codes', (state) => {
    for (const block of state.tokens) {
      if (block.type !== 'inline' || !Array.isArray(block.children)) continue
      block.children = rewriteChildren(state, block.children)
    }
    return true
  })
}

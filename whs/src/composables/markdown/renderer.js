/**
 * 全站统一 Markdown 渲染管线。
 *
 * 所有页面（含 Wiki）都通过本模块渲染 Markdown，保证：
 * - markdown-it 统一配置 { html:false, linkify:true, breaks:true }（防 XSS）；
 * - § 颜色 / 格式代码（colorCodes）全站可用；
 * - 标题自动生成去重 id，并可收集目录（Wiki 右侧大纲复用）；
 * - 图片语法中的视频 / 音频扩展名渲染为 <video> / <audio>；
 * - LaTeX（$...$ 行内、$$...$$ 块级）与 mermaid 代码块先输出占位节点，
 *   由 markdown_view.vue 在浏览器中按需懒加载 katex / mermaid 完成渲染；
 * - 代码块输出带语言标记的占位节点，由 markdown_view.vue 懒加载
 *   highlight.js 做语法高亮（覆盖绝大多数编程语言）。
 */
import MarkdownIt from 'markdown-it'
import i18n from '../../i18n'
import { colorCodesPlugin } from './colorCodes'

// ---------------------------------------------------------------------------
// 基础工具
// ---------------------------------------------------------------------------

// UTF-8 文本 -> base64（放在 data-* 属性里，避免换行 / 引号破坏 HTML）
export function encodeData(text) {
  const bytes = new TextEncoder().encode(String(text ?? ''))
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

export function decodeData(encoded) {
  if (!encoded) return ''
  const binary = atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new TextDecoder().decode(bytes)
}

export const MARKDOWN_LANGS = ['zh', 'en']

/**
 * 多语言 Markdown 内容的取文策略：渲染时始终跟随站点语言。
 * - 字符串：直接使用；
 * - { zh, en } 对象：优先当前语言，缺失时回退另一语言。
 */
export function resolveMarkdownContent(value, locale) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const lang = locale === 'en' ? 'en' : 'zh'
    const other = lang === 'en' ? 'zh' : 'en'
    return String(value[lang] || value[other] || '')
  }
  return typeof value === 'string' ? value : ''
}

// ---------------------------------------------------------------------------
// 标题 id + 目录收集
// ---------------------------------------------------------------------------

function slugifyHeading(text) {
  const base = String(text)
    .toLowerCase()
    .trim()
    .replace(/[^\w\u4e00-\u9fa5-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return base || 'section'
}

function inlineText(children) {
  if (!children) return ''
  let out = ''
  for (const token of children) {
    if (token.type === 'text' || token.type === 'code_inline') {
      out += token.content
    } else if (token.type === 'softbreak' || token.type === 'hardbreak') {
      out += ' '
    } else if (token.children) {
      out += inlineText(token.children)
    }
  }
  return out.trim()
}

function headingIdsPlugin(md) {
  md.core.ruler.push('whs_heading_ids', (state) => {
    const used = new Set()
    for (let i = 0; i < state.tokens.length; i++) {
      const token = state.tokens[i]
      if (token.type !== 'heading_open') continue
      const inline = state.tokens[i + 1]
      const text = inlineText(inline && inline.children)
      let id = slugifyHeading(text)
      const base = id
      let n = 2
      while (used.has(id)) id = `${base}-${n++}`
      used.add(id)
      token.attrSet('id', id)
      const level = parseInt(token.tag.slice(1), 10)
      if (level >= 1 && state.env && Array.isArray(state.env.outline)) {
        state.env.outline.push({ level, text, id })
      }
    }
    return true
  })
}

// ---------------------------------------------------------------------------
// LaTeX：$...$ 行内 / $$...$$ 块级
// ---------------------------------------------------------------------------

function mathInlineRule(state, silent) {
  const start = state.pos
  if (state.src[start] !== '$') return false
  // $$ 交给块级规则处理，行内仅识别单个 $
  if (state.src[start + 1] === '$') return false
  const max = state.posMax
  let pos = start + 1
  if (pos >= max || /\s/.test(state.src[pos])) return false
  let close = -1
  while (pos < max) {
    const ch = state.src[pos]
    if (ch === '\n') return false
    if (ch === '$') {
      if (state.src[pos - 1] === '\\') {
        pos++
        continue
      }
      close = pos
      break
    }
    pos++
  }
  if (close < 0 || close === start + 1) return false
  if (/\s/.test(state.src[close - 1])) return false
  const tex = state.src.slice(start + 1, close)
  if (silent) return true
  const token = state.push('math_inline', 'span', 0)
  token.content = tex
  token.markup = '$'
  state.pos = close + 1
  return true
}

function mathBlockRule(state, startLine, endLine, silent) {
  const start = state.bMarks[startLine] + state.tShift[startLine]
  const first = state.src.slice(start, state.eMarks[startLine]).trim()
  if (!first.startsWith('$$')) return false
  if (silent) return true

  let content = ''
  let nextLine = startLine + 1
  let closed = false
  const rest = first.slice(2)
  if (rest.endsWith('$$') && rest.length >= 2) {
    content = rest.slice(0, -2)
    closed = true
  } else {
    content = rest
    while (nextLine < endLine) {
      const lineStart = state.bMarks[nextLine] + state.tShift[nextLine]
      const line = state.src.slice(lineStart, state.eMarks[nextLine])
      const idx = line.indexOf('$$')
      if (idx >= 0) {
        content += `\n${line.slice(0, idx)}`
        nextLine += 1
        closed = true
        break
      }
      content += `\n${line}`
      nextLine += 1
    }
  }
  if (!closed) return false

  state.line = nextLine
  const token = state.push('math_block', 'div', 0)
  token.block = true
  token.content = content.trim()
  token.map = [startLine, nextLine]
  return true
}

// ---------------------------------------------------------------------------
// 代码块 / mermaid / 媒体
// ---------------------------------------------------------------------------

const VIDEO_EXTS = new Set(['mp4', 'webm', 'mov'])
const AUDIO_EXTS = new Set(['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac'])

// 代码块语言显示名（常见别名格式化；未收录的按原文展示）
const LANGUAGE_DISPLAY = {
  js: 'JavaScript',
  javascript: 'JavaScript',
  ts: 'TypeScript',
  typescript: 'TypeScript',
  py: 'Python',
  python: 'Python',
  sh: 'Shell',
  shell: 'Shell',
  bash: 'Bash',
  zsh: 'Zsh',
  powershell: 'PowerShell',
  ps1: 'PowerShell',
  sql: 'SQL',
  html: 'HTML',
  xml: 'XML',
  css: 'CSS',
  scss: 'SCSS',
  less: 'Less',
  json: 'JSON',
  yaml: 'YAML',
  yml: 'YAML',
  md: 'Markdown',
  markdown: 'Markdown',
  c: 'C',
  cpp: 'C++',
  'c++': 'C++',
  csharp: 'C#',
  cs: 'C#',
  java: 'Java',
  go: 'Go',
  rust: 'Rust',
  php: 'PHP',
  ruby: 'Ruby',
  kotlin: 'Kotlin',
  swift: 'Swift',
  lua: 'Lua',
  r: 'R',
  perl: 'Perl',
  dockerfile: 'Dockerfile',
  diff: 'Diff',
  ini: 'INI',
  toml: 'TOML',
  makefile: 'Makefile',
  text: 'Plain text',
  plaintext: 'Plain text',
}

/** 代码块语言显示名；未指定语言时显示“纯文本”。 */
export function displayLanguage(lang) {
  const key = String(lang || '').toLowerCase()
  if (!key) return i18n.global.t('markdown.plainText')
  return LANGUAGE_DISPLAY[key] || key
}

// 渲染规则内使用的 HTML 转义（markdown-it 已保证 html:false，这里只需处理文本内容）
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
    return map[ch]
  })
}

// 与 markdown-it 默认 image 规则一致：把 alt 内容按纯文本渲染（CommonMark 要求）
function defaultImageRender(tokens, idx, options, env, self) {
  const token = tokens[idx]
  const altIndex = token.attrIndex('alt')
  if (altIndex >= 0) token.attrs[altIndex][1] = self.renderInlineAsText(token.children, options, env)
  return self.renderToken(tokens, idx, options)
}

/** 复制按钮图标（lucide 风格内联 SVG，颜色跟随 currentColor）。 */
export const COPY_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>'

/** 复制成功后的对勾图标。 */
export const CHECK_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>'

function fenceRenderer(tokens, idx, options, env, self) {
  const token = tokens[idx]
  const source = token.content || ''
  const info = (token.info || '').trim()
  const lang = (info.split(/\s+/)[0] || '').toLowerCase()
  const escaped = escapeHtml(source)

  if (lang === 'mermaid') {
    const copyLabel = escapeHtml(i18n.global.t('markdown.copy'))
    return `<div class="md-mermaid-block"><button type="button" class="md-copy-btn md-mermaid-copy" title="${copyLabel}" aria-label="${copyLabel}">${COPY_ICON}</button><div class="md-mermaid" data-src="${encodeData(source)}"><pre class="md-mermaid-source"><code>${escaped}</code></pre></div></div>`
  }
  const copyLabel = escapeHtml(i18n.global.t('markdown.copy'))
  return `<div class="md-code-block"><div class="md-code-head"><span class="md-code-lang">${escapeHtml(displayLanguage(lang))}</span><button type="button" class="md-copy-btn md-code-copy" title="${copyLabel}" aria-label="${copyLabel}">${COPY_ICON}</button></div><pre class="md-code"><code class="hljs" data-lang="${escapeHtml(lang)}">${escaped}</code></pre></div>`
}

function imageRenderer(tokens, idx, options, env, self) {
  const token = tokens[idx]
  const src = token.attrGet('src') || ''
  const ext = (String(src).split(/[?#]/)[0].split('.').pop() || '').toLowerCase()
  const srcSafe = escapeHtml(src)
  const alt = escapeHtml(self.renderInlineAsText(token.children || [], options, env))
  const caption = alt ? `<p class="md-media-caption">${alt}</p>` : ''
  if (VIDEO_EXTS.has(ext)) {
    return `<video src="${srcSafe}" controls preload="metadata" class="md-media"></video>${caption}`
  }
  if (AUDIO_EXTS.has(ext)) {
    return `<audio src="${srcSafe}" controls preload="metadata" class="md-media"></audio>${caption}`
  }
  return defaultImageRender(tokens, idx, options, env, self)
}

// ---------------------------------------------------------------------------
// Renderer
// ---------------------------------------------------------------------------

export function createMarkdownRenderer() {
  const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
  colorCodesPlugin(md)

  md.block.ruler.before('fence', 'md_math_block', mathBlockRule, {
    alt: ['paragraph', 'reference', 'blockquote', 'list'],
  })
  md.inline.ruler.before('escape', 'md_math_inline', mathInlineRule)
  headingIdsPlugin(md)

  md.renderer.rules.math_inline = (tokens, idx) => {
    const tex = tokens[idx].content
    return `<span class="md-math" data-tex="${encodeData(tex)}">${md.utils.escapeHtml(`$${tex}$`)}</span>`
  }
  md.renderer.rules.math_block = (tokens, idx) => {
    const tex = tokens[idx].content
    return `<div class="md-math-block" data-tex="${encodeData(tex)}">${md.utils.escapeHtml(`$$${tex}$$`)}</div>`
  }

  md.renderer.rules.fence = fenceRenderer
  md.renderer.rules.image = imageRenderer

  // 外链新标签页打开
  const defaultLinkOpen =
    md.renderer.rules.link_open ||
    ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const href = tokens[idx].attrGet('href') || ''
    if (/^https?:\/\//i.test(href)) {
      tokens[idx].attrSet('target', '_blank')
      tokens[idx].attrSet('rel', 'noopener noreferrer')
    }
    return defaultLinkOpen(tokens, idx, options, env, self)
  }

  return {
    /**
     * 渲染 Markdown。
     * @param {string|object} content 原文（对象时需先按语言取文，见 resolveMarkdownContent）
     * @param {{ outline?: boolean }} [opts]
     * @returns {{ html: string, outline: Array<{level:number,text:string,id:string}> }}
     */
    render(content, opts = {}) {
      const outline = []
      const html = md.render(String(content || ''), opts.outline === false ? {} : { outline })
      return { html, outline }
    },
  }
}

// 模块级单例：全站共用同一套解析器与插件
export const siteMarkdown = createMarkdownRenderer()

/**
 * 便捷函数：按站点语言渲染（多语言对象自动取对应语言）。
 */
export function renderMarkdown(content, locale, opts) {
  return siteMarkdown.render(resolveMarkdownContent(content, locale), opts)
}

/**
 * 维基 Markdown 渲染管线（从零实现，未引入任何第三方 Wiki 项目代码）。
 *
 * - 复用全站统一的 markdown-it 配置 { html:false, linkify:true, breaks:true }（防 XSS）；
 * - 自研 core rule：渲染时给每个标题 token 附加 slug 化且去重的 id，
 *   同时从 token 流收集页面目录（h1–h6 全部进目录；h1 即页面标题，作为目录树的根）；
 * - buildOutlineTree() 把扁平目录按 h1–h6 层级组装成树，供右侧 TOC 树状渲染（层层递进）；
 * - 目录与渲染产物天然一致，无需后端参与解析；
 * - 外链自动 target="_blank" rel="noopener"。
 */
import MarkdownIt from 'markdown-it'

// 标题文本 -> 稳定的 slug 化 id（保留中文/字母/数字，其余折叠为 '-'）
function slugifyHeading(text) {
  const base = String(text)
    .toLowerCase()
    .trim()
    .replace(/[^\w\u4e00-\u9fa5-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return base || 'section'
}

// 从行内 token 链提取纯文本（用于目录标题展示）
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

// 自研 core rule：标题 id 生成 + 目录收集
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
      while (used.has(id)) {
        id = `${base}-${n++}`
      }
      used.add(id)
      token.attrSet('id', id)
      // 收集目录项（h1–h6 全部进入目录：h1 为页面标题，作为目录树的根）
      const level = parseInt(token.tag.slice(1), 10)
      if (level >= 1 && state.env && Array.isArray(state.env.outline)) {
        state.env.outline.push({ level, text, id })
      }
    }
    return true
  })
}

function createMarkdownRenderer() {
  const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
  headingIdsPlugin(md)

  // 外链新标签打开
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

  // 媒体渲染：`![描述](xxx.mp4/webm/mov)` 渲染为 <video>，
  // `![描述](xxx.mp3/wav/...)` 渲染为 <audio>（html:false 下原生标签不可用，自研规则替代）
  const VIDEO_EXTS = new Set(['mp4', 'webm', 'mov'])
  const AUDIO_EXTS = new Set(['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac'])
  const defaultImageRender =
    md.renderer.rules.image ||
    ((tokens, idx, options, env, self) => {
      const token = tokens[idx]
      const a = token.attrIndex('alt')
      if (a >= 0) token.attrs[a][1] = self.renderInlineAsText(token.children, options, env)
      return self.renderToken(tokens, idx, options)
    })
  md.renderer.rules.image = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    const src = token.attrGet('src') || ''
    const ext = (String(src).split(/[?#]/)[0].split('.').pop() || '').toLowerCase()
    const srcSafe = md.utils.escapeHtml(src)
    const alt = md.utils.escapeHtml(self.renderInlineAsText(token.children, options, env))
    const caption = alt ? `<p class="wiki-media-caption">${alt}</p>` : ''
    if (VIDEO_EXTS.has(ext)) {
      return `<video src="${srcSafe}" controls preload="metadata" class="wiki-media"></video>${caption}`
    }
    if (AUDIO_EXTS.has(ext)) {
      return `<audio src="${srcSafe}" controls preload="metadata" class="wiki-media"></audio>${caption}`
    }
    return defaultImageRender(tokens, idx, options, env, self)
  }

  return {
    /**
     * 渲染 Markdown。
     * @param {string} content Markdown 原文
     * @returns {{ html: string, outline: Array<{level:number,text:string,id:string}> }}
     *   outline 为扁平目录（h1–h6，按出现顺序）；树形结构用 buildOutlineTree() 组装
     */
    render(content) {
      const outline = []
      const html = md.render(content || '', { outline })
      return { html, outline }
    },
  }
}

// 模块级单例（与全站其他页面的 md 实例写法一致）
export const wikiMarkdown = createMarkdownRenderer()

/**
 * 把扁平目录组装成标题树（h1–h6 层层递进）。
 *
 * 规则：同级标题互成兄弟；下一个标题级别更深时挂为当前节点的子节点；
 * 级别回退（含跳级，如 h3 之后直接出现 h1）时回到对应祖先层级。
 * 首个标题不一定是 h1（如页面以 ## 开头），此时它自己就是树的根。
 *
 * @param {Array<{level:number,text:string,id:string}>} items 渲染时收集的扁平目录
 * @returns {Array<{level:number,text:string,id:string,children:Array}>} 树根节点数组
 */
export function buildOutlineTree(items) {
  const roots = []
  // 栈中保存当前祖先链（每项含 level 与 children）
  const stack = []
  for (const item of items || []) {
    const node = { ...item, children: [] }
    // 弹出级别不低于当前标题的祖先：同级（新兄弟）或更深（回退）都回到父级
    while (stack.length && stack[stack.length - 1].level >= node.level) stack.pop()
    if (stack.length) stack[stack.length - 1].children.push(node)
    else roots.push(node)
    stack.push(node)
  }
  return roots
}

<script setup>
/**
 * 全站统一 Markdown 渲染组件。
 *
 * - 使用 composables/markdown/renderer.js 的统一管线输出 HTML；
 * - 渲染后按需懒加载增强：
 *   · highlight.js 语法高亮（代码块）；
 *   · KaTeX 渲染 $...$ / $$...$$ 公式；
 *   · mermaid 渲染 ```mermaid 代码块（跟随站点明暗主题，主题切换时重绘）；
 * - 多语言内容（{ zh, en }）渲染时始终跟随站点语言；
 * - 自动为标题生成 id 并通过 outline 事件抛出目录（Wiki 大纲复用）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import 'katex/dist/katex.min.css'
import { decodeData, displayLanguage, resolveMarkdownContent, siteMarkdown, COPY_ICON, CHECK_ICON } from '../composables/markdown/renderer'
import { copyText } from '../composables/clipboard'

const props = defineProps({
  content: { type: [String, Object], default: '' },
})
const emit = defineEmits(['outline'])

const { t, locale } = useI18n()
const root = ref(null)
const html = ref('')

const source = computed(() => resolveMarkdownContent(props.content, locale.value))

function render() {
  const { html: rendered, outline } = siteMarkdown.render(source.value)
  html.value = rendered
  emit('outline', outline)
}
// 语言切换时重渲染：多语言内容会换文本，单语言内容的复制按钮文案也会更新
watch([source, () => locale.value], render, { immediate: true })

// ---------------------------------------------------------------------------
// 懒加载增强
// ---------------------------------------------------------------------------

let hljsPromise = null
let katexPromise = null
let mermaidPromise = null
let enhanceSeq = 0

function loadHljs() {
  if (!hljsPromise) hljsPromise = import('highlight.js').then((m) => m.default)
  return hljsPromise
}

function loadKatex() {
  if (!katexPromise) {
    katexPromise = import('katex').then((m) => m.default)
  }
  return katexPromise
}

function loadMermaid() {
  if (!mermaidPromise) mermaidPromise = import('mermaid').then((m) => m.default)
  return mermaidPromise
}

function isDarkTheme() {
  const html = document.documentElement
  if (html.classList.contains('dark')) return true
  if (html.classList.contains('light')) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

async function highlightCode(el, seq) {
  const blocks = [...el.querySelectorAll('pre.md-code code.hljs')].filter(
    (code) => !code.dataset.highlighted
  )
  if (!blocks.length) return
  let hljs
  try {
    hljs = await loadHljs()
  } catch {
    return
  }
  if (seq !== enhanceSeq) return
  for (const code of blocks) {
    code.dataset.highlighted = '1'
    const text = code.textContent
    const lang = (code.dataset.lang || '').toLowerCase()
    try {
      if (lang && hljs.getLanguage(lang)) {
        code.innerHTML = hljs.highlight(text, { language: lang, ignoreIllegals: true }).value
      } else if (text.trim()) {
        const result = hljs.highlightAuto(text)
        code.innerHTML = result.value
        // 未标注语言时用自动识别结果更新代码块头部的语言提示
        if (result.language) {
          const label = code.closest('.md-code-block')?.querySelector('.md-code-lang')
          if (label) label.textContent = displayLanguage(result.language)
        }
      }
    } catch {
      // 高亮失败时保留转义后的原文
    }
  }
}

async function renderMath(el, seq) {
  const nodes = [...el.querySelectorAll('.md-math[data-tex], .md-math-block[data-tex]')].filter(
    (node) => !node.dataset.mathDone
  )
  if (!nodes.length) return
  let katex
  try {
    katex = await loadKatex()
  } catch {
    return
  }
  if (seq !== enhanceSeq) return
  for (const node of nodes) {
    node.dataset.mathDone = '1'
    const tex = decodeData(node.dataset.tex)
    const displayMode = node.classList.contains('md-math-block')
    try {
      katex.render(tex, node, { displayMode, throwOnError: false, strict: false })
    } catch {
      node.textContent = tex
    }
  }
}

async function renderMermaid(el, seq, force = false) {
  const nodes = [...el.querySelectorAll('.md-mermaid[data-src]')].filter(
    (node) => force || !node.dataset.mermaidDone
  )
  if (!nodes.length) return
  let mermaid
  try {
    mermaid = await loadMermaid()
  } catch {
    return
  }
  if (seq !== enhanceSeq && !force) return
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    // mermaid 语法错误时不向页面追加自带错误图，错误由组件内部提示
    suppressErrorRendering: true,
    theme: isDarkTheme() ? 'dark' : 'default',
    fontFamily: 'inherit',
  })
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i]
    const src = decodeData(node.dataset.src)
    node.dataset.mermaidDone = '1'
    const id = `md-mermaid-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 8)}`
    try {
      const { svg } = await mermaid.render(id, src)
      if (seq !== enhanceSeq) return
      node.innerHTML = svg
    } catch {
      // 兜底清理 mermaid 可能残留在 body 上的临时错误节点
      document
        .querySelectorAll('body > svg[id^="dmermaid"], body > div[id^="dmermaid"]')
        .forEach((el) => el.remove())
      node.innerHTML = `<pre class="md-mermaid-error">${escapeHtml(src)}</pre>`
    }
  }
}

async function enhance() {
  await nextTick()
  const el = root.value
  if (!el) return
  const seq = ++enhanceSeq
  await highlightCode(el, seq)
  await renderMath(el, seq)
  await renderMermaid(el, seq)
}

// ---------------------------------------------------------------------------
// 复制按钮（代码块 / mermaid 图）
// ---------------------------------------------------------------------------

const copyTimers = new WeakMap()

async function copyWithFeedback(btn, text) {
  if (!text) return
  const ok = await copyText(text)
  if (!ok) return
  // 复制成功：图标切换为对勾，1.5s 后恢复
  btn.innerHTML = CHECK_ICON
  btn.title = t('markdown.copied')
  btn.setAttribute('aria-label', t('markdown.copied'))
  btn.classList.add('copied')
  clearTimeout(copyTimers.get(btn))
  copyTimers.set(
    btn,
    setTimeout(() => {
      btn.innerHTML = COPY_ICON
      btn.title = t('markdown.copy')
      btn.setAttribute('aria-label', t('markdown.copy'))
      btn.classList.remove('copied')
    }, 1500)
  )
}

function onRootClick(e) {
  const target = e.target instanceof Element ? e.target : null
  if (!target) return
  const btn = target.closest('.md-copy-btn')
  if (!btn) return
  if (btn.classList.contains('md-mermaid-copy')) {
    const node = btn.closest('.md-mermaid-block')?.querySelector('.md-mermaid[data-src]')
    copyWithFeedback(btn, node ? decodeData(node.dataset.src) : '')
    return
  }
  const code = btn.closest('.md-code-block')?.querySelector('pre code')
  copyWithFeedback(btn, code ? code.textContent : '')
}

// 滚轮落在代码块 / mermaid 图上时，把纵向滚动交给最近的纵向滚动容器，
// 避免行内横向滚动容器（pre / mermaid 容器）吞掉滚轮导致预览框无法滚动。
function onRootWheel(e) {
  if (!e.deltaY) return
  const target = e.target instanceof Element ? e.target : null
  if (!target || !target.closest('.md-code-block, .md-mermaid-block')) return
  let node = target.parentElement
  while (node && node !== document.body && node !== document.documentElement) {
    const style = getComputedStyle(node)
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1) {
      const down = e.deltaY > 0
      const atTop = node.scrollTop <= 0
      const atBottom = node.scrollTop + node.clientHeight >= node.scrollHeight - 1
      if ((down && atBottom) || (!down && atTop)) return
      const delta =
        e.deltaMode === 1
          ? e.deltaY * 16
          : e.deltaMode === 2
            ? e.deltaY * node.clientHeight
            : e.deltaY
      node.scrollTop += delta
      e.preventDefault()
      return
    }
    node = node.parentElement
  }
  // 没有局部的纵向滚动容器（如 Wiki 正文页）：把滚轮交给页面滚动
  const doc = document.scrollingElement || document.documentElement
  if (!doc || doc.scrollHeight <= doc.clientHeight + 1) return
  const down = e.deltaY > 0
  const atTop = window.scrollY <= 0
  const atBottom = window.scrollY + window.innerHeight >= doc.scrollHeight - 1
  if ((down && atBottom) || (!down && atTop)) return
  const delta =
    e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * window.innerHeight : e.deltaY
  window.scrollBy(0, delta)
  e.preventDefault()
}

watch(html, () => {
  enhance()
})

// 主题切换：mermaid SVG 颜色是渲染时固化的，需要重绘
let themeObserver = null
let themeTimer = null
function onThemeChange() {
  clearTimeout(themeTimer)
  themeTimer = setTimeout(async () => {
    const el = root.value
    if (!el || !el.querySelector('.md-mermaid[data-src]')) return
    await renderMermaid(el, enhanceSeq, true)
  }, 180)
}

onMounted(() => {
  enhance()
  themeObserver = new MutationObserver(onThemeChange)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
})

onBeforeUnmount(() => {
  themeObserver?.disconnect()
  clearTimeout(themeTimer)
})

defineExpose({ root })
</script>

<template>
  <div
    ref="root"
    class="md-body"
    v-html="html"
    @click="onRootClick"
    @wheel="onRootWheel"
  ></div>
</template>

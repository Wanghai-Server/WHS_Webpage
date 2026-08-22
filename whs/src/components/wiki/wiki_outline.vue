<script setup>
/**
 * 页内目录（TOC）：悬浮大纲 + 阅读进度。
 *
 * - 目录条目来自 wiki_markdown 渲染时从 Markdown 标题自动解析的 outline（h1–h6）；
 * - 通过 buildOutlineTree() 组装成标题树，树状渲染（h1 为根，逐层嵌套递进）；
 * - 滚动监听 + rAF 节流计算当前高亮项，点击平滑滚动到对应标题；
 * - 顶部细进度条跟随阅读进度；目录过长时内部滚动，高亮项自动保持可见。
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { buildOutlineTree } from '../../composables/wiki/markdown.js'
import WikiOutlineNode from './wiki_outline_node.vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

// 扁平目录 → 标题树（h1 为根，h2–h6 逐层嵌套）
const roots = computed(() => buildOutlineTree(props.items))

const activeId = ref('')
const progress = ref(0)
const railRef = ref(null)
let raf = null

function updateActive() {
  if (!props.items.length) {
    activeId.value = ''
    return
  }
  const probe = window.scrollY + 140
  let current = ''
  for (const item of props.items) {
    const el = document.getElementById(item.id)
    if (el && el.getBoundingClientRect().top + window.scrollY <= probe) {
      current = item.id
    }
  }
  if (!current) current = props.items[0].id
  activeId.value = current

  const doc = document.documentElement
  const max = doc.scrollHeight - window.innerHeight
  progress.value = max > 0 ? Math.min(100, Math.max(0, (window.scrollY / max) * 100)) : 0

  keepActiveVisible()
}

// 目录树内部滚动：让高亮条目保持在可视区域内
function keepActiveVisible() {
  const nav = railRef.value
  if (!nav || !activeId.value) return
  const el = nav.querySelector(`.toc-item.active`)
  if (!el) return
  try {
    el.scrollIntoView({ block: 'nearest' })
  } catch {
    /* 兼容不支持 nearest 的浏览器 */
  }
}

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = null
    updateActive()
  })
}

function scrollTo(item) {
  const el = document.getElementById(item.id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(() => props.items, () => updateActive(), { deep: true })

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  updateActive()
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  if (raf) cancelAnimationFrame(raf)
})
</script>

<template>
  <nav ref="railRef" class="wiki-outline" aria-label="Outline">
    <div class="outline-progress"><span :style="{ width: progress + '%' }"></span></div>
    <p v-if="!roots.length" class="outline-empty">—</p>
    <ul v-else class="outline-tree">
      <WikiOutlineNode
        v-for="node in roots"
        :key="node.id"
        :node="node"
        :active-id="activeId"
        :depth="0"
        @select="scrollTo"
      />
    </ul>
  </nav>
</template>

<style scoped>
.wiki-outline {
  padding: 0 4px 24px;
  font-size: 13px;
  /* 目录过长时内部滚动（sticky 侧栏不被撑出视口） */
  max-height: calc(100vh - 96px - 24px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--float-bg) transparent;
}

.outline-progress {
  height: 2px;
  margin-bottom: 12px;
  border-radius: 2px;
  background: var(--float-bg);
  overflow: hidden;
}

.outline-progress span {
  display: block;
  height: 100%;
  background: var(--notice-color);
  border-radius: 2px;
  transition: width 0.15s ease;
}

.outline-empty {
  margin: 0;
  color: var(--links-color);
  text-align: center;
}

/* 目录树 */
.outline-tree {
  list-style: none;
  margin: 0;
  padding: 0;
}
</style>

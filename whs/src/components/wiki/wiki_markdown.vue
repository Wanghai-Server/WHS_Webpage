<script setup>
/**
 * 维基 Markdown 渲染组件。
 *
 * - 输入 Markdown 原文，输出渲染后的 HTML（html:false 防 XSS）；
 * - 渲染时自动为标题生成 id 并解析目录，通过 outline 事件抛出；
 * - 统一承载维基正文的排版样式（标题/表格/代码块/引用/图片等）。
 */
import { ref, watch } from 'vue'
import { wikiMarkdown } from '../../composables/wiki/markdown.js'

const props = defineProps({
  content: { type: String, default: '' },
})
const emit = defineEmits(['outline'])

const html = ref('')

function renderContent() {
  const { html: rendered, outline } = wikiMarkdown.render(props.content)
  html.value = rendered
  emit('outline', outline)
}

watch(() => props.content, renderContent, { immediate: true })
</script>

<template>
  <div class="wiki-md" v-html="html"></div>
</template>

<style scoped>
/* ---------- 正文排版（文档流阅读体验） ---------- */
.wiki-md {
  color: var(--text-color);
  line-height: 1.8;
  font-size: 16px;
  word-break: break-word;
}

/* 标题：h1 为页面标题；h2+ 上边框分隔，滚动定位时留出导航高度 */
.wiki-md :deep(h1) {
  margin: 0 0 0.6em;
  font-size: 34px;
  line-height: 1.25;
  font-weight: 800;
  scroll-margin-top: 96px;
}

.wiki-md :deep(h2) {
  margin: 2em 0 0.8em;
  padding-top: 0.9em;
  border-top: 1px solid var(--float-bg);
  font-size: 24px;
  line-height: 1.35;
  font-weight: 700;
  scroll-margin-top: 96px;
}

.wiki-md :deep(h3) {
  margin: 1.6em 0 0.6em;
  font-size: 19px;
  line-height: 1.4;
  font-weight: 700;
  scroll-margin-top: 96px;
}

.wiki-md :deep(h4),
.wiki-md :deep(h5),
.wiki-md :deep(h6) {
  margin: 1.4em 0 0.5em;
  font-size: 16px;
  line-height: 1.5;
  font-weight: 700;
  scroll-margin-top: 96px;
}

.wiki-md :deep(p) {
  margin: 0.8em 0;
}

.wiki-md :deep(a) {
  color: var(--links-color);
  text-decoration: none;
  border-bottom: 1px dashed currentColor;
  transition: color 0.15s ease;
}

.wiki-md :deep(a:hover) {
  color: var(--text-color);
}

.wiki-md :deep(strong) {
  font-weight: 700;
}

.wiki-md :deep(ul),
.wiki-md :deep(ol) {
  padding-left: 1.6em;
  margin: 0.8em 0;
}

.wiki-md :deep(li) {
  margin: 0.25em 0;
}

.wiki-md :deep(li > ul),
.wiki-md :deep(li > ol) {
  margin: 0.2em 0;
}

.wiki-md :deep(blockquote) {
  margin: 1em 0;
  padding: 0.4em 1em;
  border-left: 3px solid var(--notice-color);
  background: var(--float-bg);
  border-radius: 0 10px 10px 0;
  color: var(--links-color);
}

.wiki-md :deep(blockquote p) {
  margin: 0.3em 0;
}

/* 代码 */
.wiki-md :deep(code) {
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--float-bg);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 0.9em;
}

.wiki-md :deep(pre) {
  margin: 1em 0;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--float-bg);
  border: 1px solid rgba(148, 163, 184, 0.12);
  overflow-x: auto;
  line-height: 1.6;
}

.wiki-md :deep(pre code) {
  background: transparent;
  padding: 0;
  font-size: 13.5px;
}

/* 表格（markdown-it 默认 preset 内置 GFM 表格支持） */
.wiki-md :deep(table) {
  width: 100%;
  margin: 1em 0;
  border-collapse: collapse;
  font-size: 14.5px;
}

.wiki-md :deep(th),
.wiki-md :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--float-bg);
  text-align: left;
}

.wiki-md :deep(th) {
  background: var(--float-bg);
  font-weight: 700;
}

.wiki-md :deep(tr:nth-child(even) td) {
  background: var(--float-bg);
}

/* 图片 */
.wiki-md :deep(img) {
  max-width: 100%;
  border-radius: 12px;
  margin: 0.5em 0;
}

/* 视频 / 音频（由上传媒体渲染规则生成） */
.wiki-md :deep(video.wiki-media) {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  margin: 0.5em auto;
  border-radius: 12px;
  background: var(--float-bg);
}

.wiki-md :deep(audio.wiki-media) {
  display: block;
  width: 100%;
  margin: 0.5em 0;
}

.wiki-md :deep(.wiki-media-caption) {
  margin: 4px 0 0.8em;
  font-size: 13px;
  color: var(--links-color);
  text-align: center;
}

/* 分割线 */
.wiki-md :deep(hr) {
  margin: 2em 0;
  border: none;
  border-top: 1px solid var(--float-bg);
}
</style>

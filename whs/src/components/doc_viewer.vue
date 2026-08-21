<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import mammoth from 'mammoth'
import { X, FileText, Download } from 'lucide-vue-next'

// 可复用组件：悬浮窗浏览 .docx 试卷文档（mammoth 前端解析渲染，自托管无需外部服务）
const props = defineProps({
  url: { type: String, required: true },
  title: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const { t } = useI18n()
const loading = ref(true)
const loadError = ref('')
const html = ref('')

async function loadDoc() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetch(props.url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const buffer = await res.arrayBuffer()
    const result = await mammoth.convertToHtml({ arrayBuffer: buffer })
    html.value = result.value
  } catch (e) {
    console.warn(e)
    loadError.value = t('exam.docLoadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(loadDoc)
</script>

<template>
  <div class="doc-overlay" @click.self="emit('close')">
    <div class="doc-panel">
      <header class="doc-head">
        <h3 class="doc-title">
          <FileText :size="18" />
          {{ title || t('exam.docTitle') }}
        </h3>
        <div class="doc-actions">
          <a class="doc-download" :href="url" :download="title || 'document.docx'">
            <Download :size="16" /> {{ t('exam.docDownload') }}
          </a>
          <button type="button" class="doc-close" :aria-label="t('message.close')" @click="emit('close')">
            <X :size="18" />
          </button>
        </div>
      </header>
      <div class="doc-body">
        <div v-if="loading" class="doc-state"><span class="spinner"></span>{{ t('admin.loading') }}</div>
        <div v-else-if="loadError" class="doc-state error">{{ loadError }}</div>
        <div v-else class="doc-content" v-html="html"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.doc-overlay {
  position: fixed;
  inset: 0;
  z-index: 6000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.doc-panel {
  display: flex;
  flex-direction: column;
  width: min(860px, 95vw);
  height: min(82vh, 720px);
  border-radius: 16px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.2);
  overflow: hidden;
}

.doc-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: var(--float-bg);
}

.doc-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-color);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.doc-download {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s ease;
}

.doc-download:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.doc-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
}

.doc-close:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.doc-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 26px;
}

.doc-state {
  padding: 80px 0;
  text-align: center;
  color: var(--links-color);
}

.doc-state.error {
  color: #e5484d;
}

.doc-content {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-color);
  word-break: break-word;
}

.doc-content :deep(p) {
  margin: 0 0 12px;
}

.doc-content :deep(h1),
.doc-content :deep(h2),
.doc-content :deep(h3),
.doc-content :deep(h4) {
  margin: 18px 0 10px;
  color: var(--text-color);
}

.doc-content :deep(ul),
.doc-content :deep(ol) {
  margin: 0 0 12px;
  padding-left: 22px;
}

.doc-content :deep(li) {
  margin-bottom: 4px;
}

.doc-content :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}

.doc-content :deep(table) {
  border-collapse: collapse;
  margin: 12px 0;
}

.doc-content :deep(td),
.doc-content :deep(th) {
  border: 1px solid rgba(148, 163, 184, 0.35);
  padding: 6px 10px;
}

.doc-content :deep(a) {
  color: var(--links-color);
  text-decoration: none;
}

.doc-content :deep(blockquote) {
  margin: 0 0 12px;
  padding-left: 12px;
  border-left: 3px solid rgba(148, 163, 184, 0.35);
  color: var(--links-color);
}
</style>

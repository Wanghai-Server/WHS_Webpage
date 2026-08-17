<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import { ArrowLeft, X } from 'lucide-vue-next'

const props = defineProps({
  message: { type: Object, required: true },
})
const emit = defineEmits(['close', 'back'])

const { t } = useI18n()

// Markdown 渲染（html: false 防 XSS）
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const visible = ref(true) // 控制进入/离开动画
const CLOSE_MS = 260

const title = computed(() => props.message.title || t('message.untitled'))

function renderContent(content) {
  return md.render(content || '')
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 返回消息盒
function back() {
  if (!visible.value) return
  visible.value = false
  setTimeout(() => emit('back'), CLOSE_MS)
}

// 关闭（不返回消息盒）
function close() {
  if (!visible.value) return
  visible.value = false
  setTimeout(() => emit('close'), CLOSE_MS)
}

// ESC 关闭详情
function handleKeydown(e) {
  if (e.key === 'Escape') close()
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="detail-overlay" @click.self="close">
        <div class="detail-box">
          <header class="detail-head">
            <h2 class="detail-title">{{ title }}</h2>
            <div class="head-actions">
              <button
                type="button"
                class="back-btn"
                :title="t('message.back')"
                :aria-label="t('message.back')"
                @click="back"
              >
                <ArrowLeft :size="18" />
              </button>
              <button type="button" class="head-close" :aria-label="t('message.close')" @click="close">
                <X :size="18" />
              </button>
            </div>
          </header>

          <div class="detail-meta">
            <span>{{ t('message.publishedAt') }}: {{ formatTime(props.message.created_at) }}</span>
          </div>

          <div class="detail-body">
            <div class="detail-content" v-html="renderContent(props.message.content)"></div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 外形与消息盒（message_box.vue）保持一致 */
.detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.detail-box {
  width: 80%;
  height: 80vh;
  max-width: 92vw;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  color: var(--text-color);
  border-radius: 16px;
  overflow: hidden;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--links-color);
}

.detail-title {
  margin: 0;
  font-size: 20px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.back-btn:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.head-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.head-close:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.detail-meta {
  padding: 10px 20px;
  font-size: 12px;
  color: var(--links-color);
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.detail-body {
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow-y: auto;
}

/* Markdown 渲染样式 */
.detail-content {
  color: var(--text-color);
  line-height: 1.7;
  word-break: break-word;
}

.detail-content :deep(h1),
.detail-content :deep(h2),
.detail-content :deep(h3) {
  margin: 1em 0 0.5em;
  line-height: 1.3;
}

.detail-content :deep(h1:first-child),
.detail-content :deep(h2:first-child),
.detail-content :deep(h3:first-child),
.detail-content :deep(p:first-child) {
  margin-top: 0;
}

.detail-content :deep(p) {
  margin: 0.6em 0;
}

.detail-content :deep(a) {
  color: var(--links-color);
}

.detail-content :deep(code) {
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--btn-hover);
  font-family: monospace;
}

.detail-content :deep(pre) {
  padding: 12px;
  border-radius: 10px;
  background: var(--btn-hover);
  overflow-x: auto;
}

.detail-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.detail-content :deep(blockquote) {
  margin: 0.8em 0;
  padding-left: 14px;
  border-left: 3px solid var(--links-color);
  color: var(--links-color);
}

.detail-content :deep(ul),
.detail-content :deep(ol) {
  padding-left: 1.5em;
}

.detail-content :deep(img) {
  max-width: 100%;
}
</style>

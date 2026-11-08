<script setup>
/**
 * 反馈编辑器（新建 / 编辑共用）。
 *
 * - 弹窗内填写标题、分类、Markdown 正文，支持预览；
 * - 新建：POST /api/feedback；编辑：PUT /api/feedback/{id}（仅作者本人可编辑）；
 * - 弹窗使用站内标准对话框样式（手机端自动变为底部弹层）。
 */
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from 'lucide-vue-next'
import WikiMarkdown from './wiki/wiki_markdown.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const props = defineProps({
  // 传入反馈对象时为“编辑”，为 null 时为“新建”
  feedback: { type: Object, default: null },
  // 弹窗显隐由父组件控制：保持组件常驻，才能播放统一的入场 / 退场动画
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

const CATEGORIES = ['bug', 'suggestion', 'other']

const title = ref('')
const category = ref('other')
const content = ref('')
const preview = ref(false)
const submitting = ref(false)

const isEdit = computed(() => !!props.feedback)

const categoryLabels = {
  bug: t('feedback.categoryBug'),
  suggestion: t('feedback.categorySuggestion'),
  other: t('feedback.categoryOther'),
}

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

function authHeaders(extra = {}) {
  return {
    ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
    ...extra,
  }
}

// 每次打开时重置表单（新建清空 / 编辑回填）
function resetForm() {
  if (props.feedback) {
    title.value = props.feedback.title || ''
    category.value = props.feedback.category || 'other'
    content.value = props.feedback.content || ''
  } else {
    title.value = ''
    category.value = 'other'
    content.value = ''
  }
  preview.value = false
  submitting.value = false
}

watch(
  () => props.open,
  (open) => {
    if (open) resetForm()
  }
)

async function submit() {
  if (submitting.value) return
  if (!title.value.trim()) {
    showTip('warning', t('feedback.titleRequired'))
    return
  }
  if (!content.value.trim()) {
    showTip('warning', t('feedback.contentRequired'))
    return
  }
  submitting.value = true
  try {
    const url = isEdit.value ? `/api/feedback/${props.feedback.id}` : '/api/feedback'
    const res = await fetch(url, {
      method: isEdit.value ? 'PUT' : 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        title: title.value.trim(),
        content: content.value,
        category: category.value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', isEdit.value ? t('feedback.editSuccess') : t('feedback.submitSuccess'))
      emit('saved', data)
      emit('close')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <!-- 反馈编辑框：点击空白遮罩不关闭，只能通过右上角 × 或“取消”关闭 -->
      <div v-if="open" class="dialog-overlay">
        <div class="dialog feedback-editor">
          <header class="fe-head">
            <h2 class="fe-title">{{ isEdit ? t('feedback.editTitle') : t('feedback.newTitle') }}</h2>
            <button type="button" class="fe-close" :aria-label="t('message.close')" @click="emit('close')">
              <X :size="18" />
            </button>
          </header>

          <div class="fe-body">
            <label class="float-field fe-title-field">
              <input v-model="title" type="text" placeholder=" " maxlength="200" />
              <span class="float-label">{{ t('feedback.titleLabel') }}</span>
            </label>

            <div class="fe-row">
              <span class="fe-label">{{ t('feedback.categoryLabel') }}</span>
              <div class="fe-cats" role="group" :aria-label="t('feedback.categoryLabel')">
                <button
                  v-for="c in CATEGORIES"
                  :key="c"
                  type="button"
                  class="fe-cat"
                  :class="{ active: category === c }"
                  @click="category = c"
                >{{ categoryLabels[c] }}</button>
              </div>
            </div>

            <div class="fe-content-label">
              <span class="fe-label">{{ t('feedback.contentLabel') }}</span>
              <button type="button" class="fe-preview-toggle" @click="preview = !preview">
                {{ preview ? t('feedback.backToEdit') : t('feedback.preview') }}
              </button>
            </div>

            <textarea
              v-if="!preview"
              v-model="content"
              class="fe-textarea"
              :placeholder="t('feedback.contentPlaceholder')"
              spellcheck="false"
            ></textarea>
            <div v-else class="fe-preview">
              <WikiMarkdown :content="content" />
            </div>
          </div>

          <footer class="fe-foot">
            <button type="button" class="fe-btn ghost" @click="emit('close')">{{ t('admin.cancel') }}</button>
            <button type="button" class="fe-btn primary" :disabled="submitting" @click="submit">
              <span v-if="submitting" class="spinner"></span>
              {{ isEdit ? t('feedback.save') : t('feedback.submit') }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 9600;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.dialog {
  /* 与站内其他对话框一致的半透明毛玻璃样式 */
  --float-label-bg: var(--navbar-bg);
  width: min(720px, 100%);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  color: var(--text-color);
  overflow: hidden;
}

.fe-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.fe-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.fe-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.fe-close:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.fe-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.fe-title-field > input {
  font-weight: 600;
}

.fe-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.fe-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--links-color);
}

.fe-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.fe-cat {
  padding: 7px 16px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}

.fe-cat.active {
  color: #1f2937;
  background: #ebaa28;
  border-color: transparent;
}

.fe-content-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.fe-preview-toggle {
  border: none;
  background: none;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease;
}

.fe-preview-toggle:hover {
  color: var(--text-color);
}

.fe-textarea {
  width: 100%;
  min-height: 200px;
  box-sizing: border-box;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  line-height: 1.7;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s ease;
}

.fe-textarea:focus {
  border-color: var(--text-color);
}

.fe-preview {
  max-height: 300px;
  overflow-y: auto;
  padding: 14px;
  border: 1px dashed rgba(148, 163, 184, 0.25);
  border-radius: 12px;
}

.fe-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 22px 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.fe-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 22px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s ease, background-color 0.15s ease;
}

.fe-btn.ghost {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.fe-btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.fe-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .fe-body {
    padding: 14px 16px;
  }

  .fe-head {
    padding: 16px;
  }

  .fe-foot {
    padding: 12px 16px 16px;
  }
}
</style>

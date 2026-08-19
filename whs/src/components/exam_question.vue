<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload, Check, X } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const props = defineProps({
  question: { type: Object, required: true },  // {id,type,subject,score,subjective,image,options,allow_upload}
  modelValue: { type: [String, Array], default: null },  // 已答内容
  mode: { type: String, default: 'answer' },             // 'answer' | 'review'
  attachment: { type: [String, Array], default: () => [] },  // 作答模式：服务器已保存的附件（回显，可多个）
  reviewUid: { type: Number, default: null },            // 审阅模式：目标用户 uid
  reviewScore: { type: Number, default: null },          // 审阅模式：当前得分
  reviewAttachment: { type: [String, Array], default: () => [] },  // 审阅模式：附件（可多个）
})
const emit = defineEmits(['update:modelValue', 'saved', 'score-saved'])

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

const isReview = computed(() => props.mode === 'review')

// 填空题空数（多项填空 > 1）
const blankCount = computed(() =>
  props.question.type === 'fill_blank' ? Number(props.question.blank_count) || 1 : 1
)

// 题目附图（多张；兼容旧单图字段）
const questionImages = computed(() => {
  if (Array.isArray(props.question.images)) return props.question.images
  return props.question.image ? [props.question.image] : []
})

const value = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 附件列表（作答模式：新上传的文件名 + 服务器已保存的回显；审阅模式：考生附件）
// 支持多个附件：内部统一为文件名数组，兼容旧的单字符串格式
function normalizeAttachments(value) {
  if (Array.isArray(value)) return value.filter(Boolean)
  return value ? [value] : []
}

const attachments = ref(
  normalizeAttachments(props.mode === 'answer' ? props.attachment : props.reviewAttachment)
)

// 附件预览：附件接口需要登录鉴权（Authorization 头），而 <img> 无法携带该头，
// 因此用带 token 的 fetch 逐个拉取后转成 blob URL 展示。
// 增量加载：已加载过的附件复用其 blob URL，只拉取新增的、只撤销被移除的，
// 避免上传新图片时已上传图片全部重新渲染（闪烁）。
const previewUrls = ref([])
const previewMap = new Map() // filename -> objectURL

async function ensurePreviews() {
  const list = attachments.value
  // 撤销已不在列表中的附件
  for (const [name, url] of [...previewMap]) {
    if (!list.includes(name)) {
      URL.revokeObjectURL(url)
      previewMap.delete(name)
    }
  }
  // 只加载新增的附件
  for (const name of list) {
    if (previewMap.has(name)) continue
    try {
      const res = await fetch(`/api/exam/attachment/${name}`, { headers: authHeaders() })
      if (!res.ok) continue
      const blob = await res.blob()
      previewMap.set(name, URL.createObjectURL(blob))
    } catch (e) {
      /* 单个附件加载失败不影响其余附件 */
    }
  }
  // 保持与附件列表一致的顺序
  previewUrls.value = list.map((name) => previewMap.get(name)).filter(Boolean)
}

watch(attachments, ensurePreviews, { deep: true })

// 父级回显（fetchProgress）更新时同步到本地附件列表
watch(
  () => props.attachment,
  (v) => {
    if (props.mode !== 'answer') return
    const next = normalizeAttachments(v)
    const cur = attachments.value
    if (next.join('\u0000') !== cur.join('\u0000')) {
      attachments.value = next
    }
  }
)

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

// ---------- 作答模式：保存 ----------
// 保存时机由父级控制（路由切换 / 提交 / 页面卸载前），输入只更新本地状态，
// 避免快速作答（多选连点、快速打字）时防抖定时器被取消导致答案丢失。

async function saveAnswer(keepalive = false) {
  if (isReview.value) return
  const answer = value.value
  const body = { question_id: props.question.id, answer }
  if (attachments.value.length) body.attachment = attachments.value
  const res = await fetch('/api/exam/answer', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    keepalive,
  })
  const data = await res.json().catch(() => ({}))
  if (res.ok) {
    emit('saved', { question_id: props.question.id })
  } else {
    showTip('error', localMessage(data))
  }
}

// 本题在服务器上是否已有内容（回显的答案/附件）：
// 用于区分"从未作答"与"已作答后清空"——后者需要保存空答案以覆盖服务器旧记录
const hadInitialContent = computed(() => {
  if (props.mode !== 'answer') return false
  const init = props.modelValue
  const initHas = Array.isArray(init)
    ? init.some((x) => String(x ?? '').trim() !== '')
    : String(init ?? '').trim() !== ''
  return initHas || attachments.value.length > 0
})

// 立即保存当前题；供切题/提交前调用。
// 允许空答案（清空旧答案、附件题只传附件等场景）：
// 仅当本题从未有任何内容（答案/附件都为空）时跳过，避免产生无意义记录。
async function saveNow(keepalive = false) {
  if (isReview.value) return
  const answer = value.value
  const hasAnswer = Array.isArray(answer)
    ? answer.some((x) => String(x ?? '').trim() !== '')
    : String(answer ?? '').trim() !== ''
  if (!hasAnswer && attachments.value.length === 0 && !hadInitialContent.value) return
  await saveAnswer(keepalive)
}

function toggleOption(key) {
  if (isReview.value) return
  value.value = key
}

function toggleMulti(key) {
  if (isReview.value) return
  const cur = Array.isArray(value.value) ? [...value.value] : []
  const i = cur.indexOf(key)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(key)
  value.value = cur
}

// 多项填空：写入第 i 个空的答案（value 为每空字符串组成的数组）
function setBlankValue(i, text) {
  const arr = Array.isArray(value.value) ? [...value.value] : []
  arr[i] = text
  value.value = arr
}

// 上传附件（仅填空题 allow_upload）；与后端 MAX_EXAM_UPLOAD_SIZE 保持一致（20MB）
const MAX_UPLOAD_SIZE = 20 * 1024 * 1024
const uploading = ref(false)

async function onFileChange(event) {
  if (isReview.value || uploading.value) return
  const f = event.target.files && event.target.files[0]
  if (!f) return
  if (f.size > MAX_UPLOAD_SIZE) {
    showTip('warning', t('exam.uploadTooLarge'))
    event.target.value = ''
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('question_id', props.question.id)
    fd.append('file', f)
    const res = await fetch('/api/exam/upload', {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      // 追加到附件列表（支持多个附件）；切题/提交时随答案一起保存
      attachments.value.push(data.attachment)
      showTip('info', t('exam.uploaded'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

// 删除某张已上传的附件（仅作答模式）：后端删除文件与记录引用，本地同步移除
const removingAttachment = ref('')

async function removeAttachment(name) {
  if (isReview.value || removingAttachment.value) return
  removingAttachment.value = name
  try {
    const res = await fetch(`/api/exam/attachment/${name}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      attachments.value = attachments.value.filter((x) => x !== name)
      showTip('info', t('exam.attachmentRemoved'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    removingAttachment.value = ''
  }
}

// 大图预览：点击附件缩略图展开完整图片
const lightboxUrl = ref('')

function openLightbox(url) {
  lightboxUrl.value = url
}

function closeLightbox() {
  lightboxUrl.value = ''
}

// ESC：优先关闭大图预览
function handleKeydown(e) {
  if (e.key === 'Escape' && lightboxUrl.value) {
    closeLightbox()
  }
}

// ---------- 审阅模式：修改实际得分 ----------
const reviewScoreInput = ref(props.reviewScore ?? 0)
const savingScore = ref(false)

async function saveReviewScore() {
  const score = Number(reviewScoreInput.value)
  if (!Number.isInteger(score) || score < 0 || score > props.question.score) {
    showTip('warning', t('exam.scoreInvalid'))
    return
  }
  if (savingScore.value) return
  savingScore.value = true
  try {
    const res = await fetch('/api/admin/exam/score', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ uid: props.reviewUid, question_id: props.question.id, score }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('exam.scoreSaved'))
      emit('score-saved', { question_id: props.question.id, score, passed: data.passed })
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    savingScore.value = false
  }
}

// 页面刷新/关闭前兜底保存（keepalive 允许请求在页面卸载后继续发出）
function handleBeforeUnload() {
  if (isReview.value) return
  const answer = value.value
  const hasAnswer = Array.isArray(answer)
    ? answer.some((x) => String(x ?? '').trim() !== '')
    : String(answer ?? '').trim() !== ''
  if (!hasAnswer && attachments.value.length === 0 && !hadInitialContent.value) return
  saveAnswer(true)
}

onMounted(() => {
  ensurePreviews()
  document.addEventListener('beforeunload', handleBeforeUnload)
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('beforeunload', handleBeforeUnload)
  document.removeEventListener('keydown', handleKeydown)
  for (const url of previewMap.values()) {
    URL.revokeObjectURL(url)
  }
  previewMap.clear()
  previewUrls.value = []
})

// 暴露保存方法：父级在路由切换 / 提交前调用
defineExpose({ saveNow })
</script>

<template>
  <div class="exam-question">
    <div class="q-head">
      <span class="q-idx">{{ t('exam.questionNo', { n: question.id }) }}</span>
      <span class="q-score">{{ t('exam.scoreLabel', { n: question.score }) }}</span>
      <span v-if="question.subjective" class="q-subj">{{ t('exam.subjective') }}</span>
    </div>

    <div class="q-subject">
      {{ question.subject }}
      <div v-if="questionImages.length" class="q-images">
        <img
          v-for="(src, i) in questionImages"
          :key="i"
          :src="src"
          class="q-image"
          alt="question image"
        />
      </div>
    </div>

    <!-- 单选题 -->
    <div v-if="question.type === 'single_choice'" class="q-options">
      <label
        v-for="opt in question.options"
        :key="opt.key"
        class="q-option"
        :class="{ selected: value === opt.key, review: isReview && value === opt.key }"
      >
        <input type="radio" :checked="value === opt.key" :disabled="isReview" @change="toggleOption(opt.key)" />
        <span class="opt-text">{{ opt.text }}</span>
        <img v-if="opt.image" :src="opt.image" class="opt-image" alt="option image" />
      </label>
    </div>

    <!-- 多选题 -->
    <div v-else-if="question.type === 'multiple_choice'" class="q-options">
      <label
        v-for="opt in question.options"
        :key="opt.key"
        class="q-option"
        :class="{ selected: (value || []).includes(opt.key), review: isReview && (value || []).includes(opt.key) }"
      >
        <input
          type="checkbox"
          :checked="(value || []).includes(opt.key)"
          :disabled="isReview"
          @change="toggleMulti(opt.key)"
        />
        <span class="opt-text">{{ opt.text }}</span>
        <img v-if="opt.image" :src="opt.image" class="opt-image" alt="option image" />
      </label>
    </div>

    <!-- 填空题（支持多项填空：一道题多个空） -->
    <div v-else-if="question.type === 'fill_blank'">
      <div v-if="blankCount > 1" class="q-blanks">
        <div v-for="i in blankCount" :key="i" class="q-blank-row">
          <span class="q-blank-idx">{{ i }}.</span>
          <input
            :value="(value || [])[i - 1] ?? ''"
            type="text"
            class="q-input"
            :disabled="isReview"
            @input="setBlankValue(i - 1, $event.target.value)"
          />
        </div>
      </div>
      <input
        v-else
        :value="value ?? ''"
        type="text"
        class="q-input"
        :disabled="isReview"
        @input="value = $event.target.value"
      />
      <div v-if="question.allow_upload" class="q-upload">
        <label v-if="!isReview" class="upload-label" :class="{ busy: uploading }">
          <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" :disabled="uploading" @change="onFileChange" />
          <span v-if="uploading" class="spinner"></span>
          <Upload v-else :size="16" />
          <span>{{ t('exam.uploadLabel') }}</span>
        </label>
        <div v-if="previewUrls.length" class="upload-previews">
          <div v-for="(src, i) in previewUrls" :key="i" class="upload-preview-wrap">
            <img
              :src="src"
              class="upload-preview"
              :alt="t('exam.uploadLabel')"
              @click="openLightbox(src)"
            />
            <!-- 考生可叉掉已上传的图片（审阅模式不显示） -->
            <button
              v-if="!isReview"
              type="button"
              class="upload-remove"
              :disabled="removingAttachment !== ''"
              :title="t('exam.removeAttachment')"
              :aria-label="t('exam.removeAttachment')"
              @click.stop="removeAttachment(attachments[i])"
            >
              <span v-if="removingAttachment === attachments[i]" class="spinner"></span>
              <X v-else :size="13" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 主观题 -->
    <div v-else>
      <textarea
        :value="value ?? ''"
        class="q-textarea"
        :disabled="isReview"
        @input="value = $event.target.value"
      ></textarea>
    </div>

    <!-- 审阅模式：修改实际得分 -->
    <div v-if="isReview" class="q-review">
      <label class="review-label">{{ t('exam.reviewScore') }}</label>
      <input v-model.number="reviewScoreInput" type="number" min="0" :max="question.score" class="review-input" />
      <button type="button" class="review-save" :disabled="savingScore" @click="saveReviewScore">
        <span v-if="savingScore" class="spinner"></span>
        <Check v-else :size="15" />
        <span>{{ t('exam.saveScore') }}</span>
      </button>
    </div>
  </div>

  <!-- 大图预览悬浮窗：点击附件缩略图展开完整图片 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="lightboxUrl" class="lightbox-overlay" @click.self="closeLightbox">
        <img :src="lightboxUrl" class="lightbox-img" alt="attachment" />
        <button type="button" class="lightbox-close" :aria-label="t('message.close')" @click="closeLightbox">
          <X :size="22" />
        </button>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.exam-question {
  padding: 20px 24px;
  border-radius: 16px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
}

.q-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.q-idx {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-color);
}

.q-score {
  font-size: 13px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--btn-hover);
  color: var(--links-color);
}

.q-subj {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.q-subject {
  font-size: 16px;
  line-height: 1.6;
  color: var(--text-color);
  margin-bottom: 16px;
  white-space: pre-wrap;
}

.q-images {
  display: flex;
  flex-direction: column;
  gap: 10px;
  /* 防止 flex 交叉轴 stretch 把图片横向拉伸变形（保持原比例） */
  align-items: flex-start;
}

.q-image {
  display: block;
  max-width: 100%;
  max-height: 320px;
  margin-top: 10px;
  border-radius: 10px;
}

.q-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.q-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.q-option:hover {
  background: var(--btn-hover);
}

.q-option.selected {
  border-color: var(--text-color);
  background: var(--btn-hover);
}

.q-option input {
  accent-color: var(--text-color);
  flex-shrink: 0;
}

.opt-text {
  flex: 1;
  color: var(--text-color);
}

.opt-image {
  max-height: 60px;
  max-width: 90px;
  border-radius: 8px;
  /* 防止选项文字过长时 flex 压缩图片宽度导致变形 */
  flex-shrink: 0;
}

.q-input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  outline: none;
}

.q-input:focus {
  border-color: var(--text-color);
}

/* 多项填空：每题一空一行 */
.q-blanks {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.q-blank-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.q-blank-idx {
  font-size: 14px;
  font-weight: 700;
  color: var(--links-color);
  flex-shrink: 0;
}

.q-textarea {
  width: 100%;
  box-sizing: border-box;
  min-height: 140px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  line-height: 1.6;
  resize: vertical;
  outline: none;
}

.q-textarea:focus {
  border-color: var(--text-color);
}

.q-upload {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 12px;
}

.upload-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px dashed rgba(148, 163, 184, 0.45);
  color: var(--links-color);
  cursor: pointer;
  font-size: 13px;
  transition: border-color 0.2s ease, color 0.2s ease;
}

.upload-label:hover {
  border-color: var(--text-color);
  color: var(--text-color);
}

.upload-label.busy {
  opacity: 0.6;
  pointer-events: none;
}

.upload-label input {
  display: none;
}

.upload-previews {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

/* 单张附件缩略图：相对定位，右上角删除按钮 */
.upload-preview-wrap {
  position: relative;
  display: inline-flex;
  cursor: zoom-in;
}

.upload-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: #ffffff;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.upload-remove:hover {
  background: #e5484d;
}

.upload-preview {
  max-height: 120px;
  max-width: 180px;
  border-radius: 10px;
  /* 保持原比例展示：不裁切，也不被 flex 压缩变形 */
  flex-shrink: 0;
  display: block;
}

/* 大图预览悬浮窗 */
.lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  cursor: zoom-out;
}

.lightbox-img {
  max-width: 92vw;
  max-height: 92vh;
  border-radius: 12px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
  object-fit: contain;
}

.lightbox-close {
  position: fixed;
  top: 24px;
  right: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: #ffffff;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.lightbox-close:hover {
  background: #e5484d;
}

.q-review {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed rgba(148, 163, 184, 0.25);
}

.review-label {
  font-size: 14px;
  color: var(--links-color);
}

.review-input {
  width: 90px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  outline: none;
}

.review-input:focus {
  border-color: var(--text-color);
}

.review-save {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 10px;
  background: var(--text-color);
  color: var(--bg-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
</style>

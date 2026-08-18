<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload, Check } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const props = defineProps({
  question: { type: Object, required: true },  // {id,type,subject,score,subjective,image,options,allow_upload}
  modelValue: { type: [String, Array], default: null },  // 已答内容
  mode: { type: String, default: 'answer' },             // 'answer' | 'review'
  attachment: { type: String, default: '' },             // 作答模式：服务器已保存的附件文件名（回显）
  reviewUid: { type: Number, default: null },            // 审阅模式：目标用户 uid
  reviewScore: { type: Number, default: null },          // 审阅模式：当前得分
  reviewAttachment: { type: String, default: '' },       // 审阅模式：附件文件名
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

// 附件（作答模式：新上传的文件名，或服务器已保存的回显文件名；审阅模式：考生附件）
const attachment = ref(props.mode === 'answer' ? props.attachment : props.reviewAttachment)

// 附件预览：附件接口需要登录鉴权（Authorization 头），而 <img> 无法携带该头，
// 因此用带 token 的 fetch 拉取后转成 blob URL 展示；上传成功 / 回显变化时自动刷新。
const previewUrl = ref('')
let previewObjectUrl = null

async function loadAttachmentPreview() {
  const name = attachment.value
  if (!name) {
    previewUrl.value = ''
    return
  }
  try {
    const res = await fetch(`/api/exam/attachment/${name}`, { headers: authHeaders() })
    if (!res.ok) {
      previewUrl.value = ''
      return
    }
    const blob = await res.blob()
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl)
    previewObjectUrl = URL.createObjectURL(blob)
    previewUrl.value = previewObjectUrl
  } catch (e) {
    previewUrl.value = ''
  }
}

watch(attachment, loadAttachmentPreview)

// 父级回显（fetchProgress）更新时同步到本地附件名
watch(
  () => props.attachment,
  (v) => {
    if (props.mode === 'answer' && v && v !== attachment.value) {
      attachment.value = v
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

// ---------- 作答模式：自动保存 ----------
let saveTimer = null

function scheduleSave() {
  if (isReview.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(saveAnswer, 400)
}

async function saveAnswer() {
  if (isReview.value) return
  const answer = value.value
  const body = { question_id: props.question.id, answer }
  if (attachment.value) body.attachment = attachment.value
  const res = await fetch('/api/exam/answer', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (res.ok) {
    emit('saved', { question_id: props.question.id })
  } else {
    showTip('error', localMessage(data))
  }
}

function toggleOption(key) {
  if (isReview.value) return
  value.value = key
  scheduleSave()
}

function toggleMulti(key) {
  if (isReview.value) return
  const cur = Array.isArray(value.value) ? [...value.value] : []
  const i = cur.indexOf(key)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(key)
  value.value = cur
  scheduleSave()
}

// 多项填空：写入第 i 个空的答案（value 为每空字符串组成的数组）
function setBlankValue(i, text) {
  const arr = Array.isArray(value.value) ? [...value.value] : []
  arr[i] = text
  value.value = arr
  scheduleSave()
}

// 上传附件（仅填空题 allow_upload）；与后端 MAX_EXAM_UPLOAD_SIZE 保持一致（20MB）
const MAX_UPLOAD_SIZE = 20 * 1024 * 1024

async function onFileChange(event) {
  if (isReview.value) return
  const f = event.target.files && event.target.files[0]
  if (!f) return
  if (f.size > MAX_UPLOAD_SIZE) {
    showTip('warning', t('exam.uploadTooLarge'))
    event.target.value = ''
    return
  }
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
    attachment.value = data.attachment
    showTip('info', t('exam.uploaded'))
    // 仅当已填写答案时才保存；答案为空时等填写后随答案一起保存
    // （避免向后端提交空答案触发"答案格式不合法"）
    const hasAnswer = Array.isArray(value.value)
      ? value.value.some((x) => String(x ?? '').trim() !== '')
      : String(value.value ?? '').trim() !== ''
    // 立即保存（不走防抖）：避免考生在防抖窗口内切题导致附件从未入库
    if (hasAnswer) await saveAnswer()
  } else {
    showTip('error', localMessage(data))
  }
}

// ---------- 审阅模式：修改实际得分 ----------
const reviewScoreInput = ref(props.reviewScore ?? 0)

async function saveReviewScore() {
  const score = Number(reviewScoreInput.value)
  if (!Number.isInteger(score) || score < 0 || score > props.question.score) {
    showTip('warning', t('exam.scoreInvalid'))
    return
  }
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
}

onMounted(() => {
  loadAttachmentPreview()
})

onUnmounted(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl)
    previewObjectUrl = null
  }
})
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
        @input="value = $event.target.value; scheduleSave()"
      />
      <div v-if="question.allow_upload" class="q-upload">
        <label v-if="!isReview" class="upload-label">
          <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" @change="onFileChange" />
          <Upload :size="16" />
          <span>{{ t('exam.uploadLabel') }}</span>
        </label>
        <img v-if="previewUrl" :src="previewUrl" class="upload-preview" alt="attachment" />
      </div>
    </div>

    <!-- 主观题 -->
    <div v-else>
      <textarea
        :value="value ?? ''"
        class="q-textarea"
        :disabled="isReview"
        @input="value = $event.target.value; scheduleSave()"
      ></textarea>
    </div>

    <!-- 审阅模式：修改实际得分 -->
    <div v-if="isReview" class="q-review">
      <label class="review-label">{{ t('exam.reviewScore') }}</label>
      <input v-model.number="reviewScoreInput" type="number" min="0" :max="question.score" class="review-input" />
      <button type="button" class="review-save" @click="saveReviewScore">
        <Check :size="15" />
        <span>{{ t('exam.saveScore') }}</span>
      </button>
    </div>
  </div>
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

.upload-label input {
  display: none;
}

.upload-preview {
  max-height: 120px;
  max-width: 180px;
  border-radius: 10px;
  /* 保持原比例展示：不裁切，也不被 flex 压缩变形 */
  flex-shrink: 0;
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

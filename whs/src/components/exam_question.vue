<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload, Check } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const props = defineProps({
  question: { type: Object, required: true },  // {id,type,subject,score,subjective,image,options,allow_upload}
  modelValue: { type: [String, Array], default: null },  // 已答内容
  mode: { type: String, default: 'answer' },             // 'answer' | 'review'
  reviewUid: { type: Number, default: null },            // 审阅模式：目标用户 uid
  reviewScore: { type: Number, default: null },          // 审阅模式：当前得分
  reviewAttachment: { type: String, default: '' },       // 审阅模式：附件文件名
})
const emit = defineEmits(['update:modelValue', 'saved', 'score-saved'])

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

const isReview = computed(() => props.mode === 'review')

const value = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 附件（作答模式新上传的文件名）
const attachment = ref(props.mode === 'answer' ? '' : props.reviewAttachment)
const attachmentSrc = computed(() => {
  const name = attachment.value || props.reviewAttachment
  return name ? `/api/exam/attachment/${name}` : ''
})

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

// 上传附件（仅填空题 allow_upload）
async function onFileChange(event) {
  if (isReview.value) return
  const f = event.target.files && event.target.files[0]
  if (!f) return
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
    scheduleSave()
    showTip('info', t('exam.uploaded'))
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
    emit('score-saved', { question_id: props.question.id, score })
  } else {
    showTip('error', localMessage(data))
  }
}

onUnmounted(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
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
      <img v-if="question.image" :src="question.image" class="q-image" alt="question image" />
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

    <!-- 填空题 -->
    <div v-else-if="question.type === 'fill_blank'">
      <input
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
        <img v-if="attachmentSrc" :src="attachmentSrc" class="upload-preview" alt="attachment" />
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
  object-fit: cover;
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

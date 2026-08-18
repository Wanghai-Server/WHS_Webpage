<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import { FileText } from 'lucide-vue-next'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import ExamQuestion from '../components/exam_question.vue'
import DocViewer from '../components/doc_viewer.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const { state: authState, fetchMe } = useAuth()
const { showTip } = useTips()

// Markdown 渲染（试卷说明 tips；html: false 防 XSS）
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
function renderTips(content) {
  return md.render(content || '')
}

// 阶段：notice（试卷说明）-> profile（个人信息）-> answering（答题）-> done（完成）
const stage = ref('notice')
const loading = ref(true)

// 试卷说明文档悬浮窗
const showDocViewer = ref(false)

// 个人信息
const profile = ref({ player_name: '', qq_name: '', qq_number: '', attempts: 0, passed: false, can_answer: true })
const playerName = ref('')
const qqName = ref('')
const qqNumber = ref('')
let profileTimer = null

// 重审申请（防连点）：本答卷周期内只允许申请一次；重做（新答卷周期）后重置
const reviewRequested = ref(false)
const reviewing = ref(false)

// 考试数据
const examConfig = ref(null)   // {total_score, questions}
const progress = ref(null)     // {answered, answered_count, all_answered}
// 每题答案（本地维护，回显 + 组件 v-model 双向绑定）
const answers = ref({})
// 每题已上传附件文件名（从服务器进度回显，供重新进入题目时展示）
const attachments = ref({})

const questionIds = computed(() => (examConfig.value ? examConfig.value.questions.map((q) => q.id) : []))
const currentId = ref(null)
const currentQuestion = computed(
  () => examConfig.value?.questions.find((q) => q.id === currentId.value) || null
)
const currentAnswer = computed(() => answers.value[currentId.value] ?? null)

const profileComplete = computed(() => playerName.value.trim() !== '' && qqName.value.trim() !== '' && qqNumber.value.trim() !== '')

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

async function fetchExam() {
  const res = await fetch('/api/exam', { headers: authHeaders() })
  const data = await res.json().catch(() => ({}))
  if (res.ok) examConfig.value = data
  else showTip('error', localMessage(data))
}

async function fetchProgress() {
  const res = await fetch('/api/exam/progress', { headers: authHeaders() })
  const data = await res.json().catch(() => ({}))
  if (res.ok) {
    progress.value = data
    // 用已答内容回显每题答案与附件
    for (const [qid, rec] of Object.entries(data.answered || {})) {
      answers.value[qid] = rec.answer
      attachments.value[qid] = rec.attachment || ''
    }
  }
  return data
}

async function fetchAll() {
  loading.value = true
  try {
    const res = await fetch('/api/exam/profile', { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showTip('error', localMessage(data))
      return
    }
    profile.value = data
    playerName.value = data.player_name || ''
    qqName.value = data.qq_name || ''
    qqNumber.value = data.qq_number || ''
    // 从后端同步本答卷周期的重审申请状态（刷新页面后仍保持禁用）
    reviewRequested.value = !!data.review_requested
    await fetchExam()
    await fetchProgress()
    if (examConfig.value && questionIds.value.length) {
      currentId.value = Number(route.query.question) || questionIds.value[0]
    }
    // 已通过 / 次数用完 -> 直接完成页；否则先看试卷说明
    if (profile.value.passed || (!profile.value.can_answer && profile.value.attempts >= 2)) {
      stage.value = 'done'
    } else {
      stage.value = 'notice'
    }
  } finally {
    loading.value = false
  }
}

// 个人信息实时保存（防抖）
function scheduleProfileSave() {
  if (profileTimer) clearTimeout(profileTimer)
  profileTimer = setTimeout(saveProfile, 500)
}

async function saveProfile() {
  await fetch('/api/exam/profile', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      player_name: playerName.value.trim(),
      qq_name: qqName.value.trim(),
      qq_number: qqNumber.value.trim(),
    }),
  })
}

function startAnswer() {
  if (!profileComplete.value) {
    showTip('warning', t('exam.profileRequired'))
    return
  }
  stage.value = 'answering'
}

// 答题导航（navRoutes 供导航栏使用）
const navRoutes = computed(() => {
  if (stage.value !== 'answering') return null
  const ids = questionIds.value
  const idx = ids.indexOf(currentId.value)
  const prev = idx > 0 ? ids[idx - 1] : null
  const next = idx < ids.length - 1 ? ids[idx + 1] : null
  return {
    prev: { label: `← ${t('exam.prev')}`, route: prev ? `/joinus/exam?question=${prev}` : '' },
    current: { label: `${currentId.value} / ${ids.length}`, route: '' },
    next: { label: `${t('exam.next')} →`, route: next ? `/joinus/exam?question=${next}` : '' },
  }
})

// 某题已保存：刷新进度，若全部答完则自动交卷
async function onAnswerSaved() {
  const p = await fetchProgress()
  if (p && p.all_answered) {
    finishExam()
  }
}

async function finishExam() {
  const res = await fetch('/api/exam/finish', { method: 'POST', headers: authHeaders() })
  const data = await res.json().catch(() => ({}))
  if (res.ok) {
    profile.value.attempts = data.attempts
    profile.value.passed = data.passed
    profile.value.can_answer = data.can_answer
    stage.value = 'done'
    // 交卷（及格后权限升级为 player=2）：刷新公共用户数据，
    // 使首页等处的"正式成员"判断立即生效
    fetchMe()
  } else {
    showTip('error', localMessage(data))
  }
}

// 完成页得分（从进度汇总）
const obtainedScore = computed(() => {
  const answered = progress.value?.answered || {}
  return Object.values(answered).reduce((sum, r) => sum + (r.obtained_score || 0), 0)
})

async function retake() {
  const res = await fetch('/api/exam/reset', { method: 'POST', headers: authHeaders() })
  const data = await res.json().catch(() => ({}))
  if (res.ok) {
    answers.value = {}
    attachments.value = {}
    reviewRequested.value = false // 新答卷周期：允许再申请一次重审
    await fetchProgress()
    currentId.value = questionIds.value[0]
    router.replace('/joinus/exam?question=' + questionIds.value[0])
    stage.value = 'answering'
    showTip('info', t('exam.retakeStarted'))
  } else {
    showTip('error', localMessage(data))
  }
}

async function requestReview() {
  // 防连点：本答卷周期已申请过 / 请求进行中时忽略重复点击
  if (reviewRequested.value || reviewing.value) return
  reviewing.value = true
  try {
    const res = await fetch('/api/exam/review', { method: 'POST', headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      reviewRequested.value = true
      showTip('info', t('exam.reviewSent'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    reviewing.value = false
  }
}

watch(
  () => route.query.question,
  (q) => {
    if (stage.value === 'answering' && questionIds.value.length) {
      const id = Number(q)
      if (questionIds.value.includes(id)) currentId.value = id
    }
  }
)

onMounted(fetchAll)

onUnmounted(() => {
  if (profileTimer) {
    clearTimeout(profileTimer)
    profileTimer = null
  }
})
</script>

<template>
  <Top_navbar back-route="/joinus" :nav-routes="navRoutes" />

  <main class="exam-page">
    <div v-if="loading" class="placeholder">{{ t('admin.loading') }}</div>

    <!-- 试卷说明（看完后才能填写个人信息并开始答题） -->
    <template v-else-if="stage === 'notice'">
      <section class="exam-card load-in">
        <h1 class="exam-title">{{ t('exam.noticeTitle') }}</h1>
        <div v-if="examConfig?.tips" class="notice-content" v-html="renderTips(examConfig.tips)"></div>
        <p v-else class="notice-empty">{{ t('exam.noticeEmpty') }}</p>
        <button
          v-if="examConfig?.tips_doc"
          type="button"
          class="doc-view-btn"
          @click="showDocViewer = true"
        >
          <FileText :size="16" /> {{ t('exam.docView') }}
        </button>
        <button type="button" class="start-btn" @click="stage = 'profile'">
          {{ t('exam.noticeNext') }}
        </button>
      </section>

      <!-- 试卷文档悬浮窗 -->
      <DocViewer
        v-if="showDocViewer"
        :url="examConfig.tips_doc"
        @close="showDocViewer = false"
      />
    </template>

    <!-- 个人信息 -->
    <template v-else-if="stage === 'profile'">
      <section class="exam-card load-in">
        <h1 class="exam-title">{{ t('exam.profileTitle') }}</h1>
        <div class="field">
          <label class="label">{{ t('exam.playerName') }}</label>
          <input
            v-model="playerName"
            type="text"
            :placeholder="t('exam.playerNamePlaceholder')"
            @input="scheduleProfileSave"
          />
        </div>
        <div class="field">
          <label class="label">{{ t('exam.qqName') }}</label>
          <input v-model="qqName" type="text" :placeholder="t('exam.qqName')" @input="scheduleProfileSave" />
        </div>
        <div class="field">
          <label class="label">{{ t('exam.qqNumber') }}</label>
          <input v-model="qqNumber" type="text" :placeholder="t('exam.qqNumber')" @input="scheduleProfileSave" />
        </div>
        <button type="button" class="start-btn" :disabled="!profileComplete" @click="startAnswer">
          {{ t('exam.startAnswer') }}
        </button>
      </section>
    </template>

    <!-- 答题 -->
    <template v-else-if="stage === 'answering'">
      <ExamQuestion
        v-if="currentQuestion"
        :key="currentId"
        :question="currentQuestion"
        :model-value="currentAnswer"
        :attachment="attachments[currentId] || ''"
        :mode="'answer'"
        @update:model-value="(v) => { answers[currentId] = v }"
        @saved="onAnswerSaved"
      />
      <div class="answer-hint">{{ t('exam.autoSaveHint') }}</div>
    </template>

    <!-- 完成 -->
    <template v-else>
      <section class="exam-card load-in done-card">
        <h1 class="exam-title">{{ t('exam.doneTitle') }}</h1>
        <div class="score-box" :class="{ passed: profile.passed }">
          <p class="score-line">{{ t('exam.totalScore', { total: examConfig?.total_score ?? 0, obtained: obtainedScore }) }}</p>
          <p class="verdict">
            {{ profile.passed ? t('exam.passed') : t('exam.failed') }}
          </p>
        </div>

        <!-- 仅不及格时显示操作区；及格后成绩单只展示成绩 -->
        <div v-if="!profile.passed" class="done-actions">
          <button v-if="profile.attempts < 2" type="button" class="btn retake" @click="retake">{{ t('exam.retake') }}</button>
          <button
            type="button"
            class="btn review"
            :disabled="reviewRequested || reviewing"
            @click="requestReview"
          >{{ reviewRequested ? t('exam.reviewRequested') : t('exam.reviewRequest') }}</button>
        </div>
        <p v-if="!profile.passed && profile.attempts >= 2" class="exhausted-hint">{{ t('exam.exhausted') }}</p>
      </section>
    </template>
  </main>

  <Page_footer />
</template>

<style scoped>
.exam-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 100px 24px 40px;
  box-sizing: border-box;
  min-height: 60vh;
}

.placeholder {
  padding: 120px 0;
  text-align: center;
  color: var(--links-color);
}

.exam-card {
  padding: 28px;
  border-radius: 20px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

.exam-title {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-color);
  text-align: center;
}

/* 试卷说明（Markdown 渲染） */
.notice-content {
  margin-bottom: 20px;
  text-align: left;
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-color);
  word-break: break-word;
}

.notice-content :deep(p) {
  margin: 0 0 12px;
}

.notice-content :deep(h1),
.notice-content :deep(h2),
.notice-content :deep(h3) {
  margin: 16px 0 10px;
  color: var(--text-color);
}

.notice-content :deep(ul),
.notice-content :deep(ol) {
  margin: 0 0 12px;
  padding-left: 22px;
}

.notice-content :deep(li) {
  margin-bottom: 4px;
}

.notice-content :deep(img) {
  max-width: 100%;
  border-radius: 10px;
  margin: 8px 0;
}

.notice-content :deep(a) {
  color: var(--links-color);
}

.notice-content :deep(code) {
  background: var(--btn-hover);
  padding: 2px 6px;
  border-radius: 6px;
  font-size: 13px;
}

.notice-content :deep(pre) {
  background: var(--btn-hover);
  padding: 12px;
  border-radius: 10px;
  overflow-x: auto;
}

.notice-empty {
  margin: 0 0 20px;
  text-align: center;
  color: var(--links-color);
}

/* 查看试卷文档按钮 */
.doc-view-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 14px;
  transition: all 0.15s ease;
}

.doc-view-btn:hover {
  color: var(--text-color);
  background: var(--btn-hover);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.label {
  font-size: 14px;
  color: var(--links-color);
}

.field input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  outline: none;
  transition: border-color 0.2s ease;
}

.field input:focus {
  border-color: var(--text-color);
}

.start-btn {
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: 12px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.2s ease, opacity 0.2s ease;
}

.start-btn:hover {
  background: #d99a1f;
}

.start-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.answer-hint {
  margin-top: 14px;
  text-align: center;
  font-size: 13px;
  color: var(--links-color);
}

.done-card {
  text-align: center;
}

.score-box {
  padding: 20px;
  border-radius: 16px;
  background: var(--btn-hover);
  margin-bottom: 20px;
}

.score-box.passed {
  background: rgba(46, 158, 91, 0.12);
}

.score-line {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-color);
}

.verdict {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}

.exhausted-hint {
  margin: 0 0 16px;
  color: #e5484d;
  font-size: 14px;
}

.done-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-bottom: 14px;
}

.btn {
  padding: 12px 24px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.btn.retake {
  background: var(--text-color);
  color: var(--bg-color);
}

.btn.review {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.35);
  color: var(--links-color);
}

.btn.review:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Users,
  FileText,
  BookOpen,
  Eye,
  Ban,
  CircleCheck,
  LockOpen,
  Shield,
  Trash2,
  ChevronLeft,
  ChevronRight,
  UserRound,
  Search,
  MessageSquare,
  X,
} from 'lucide-vue-next'
import ExamQuestion from './exam_question.vue'
import ExamEditor from './exam_editor.vue'
import StatusDropdown from './status_dropdown.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { useDialogBox } from '../composables/useDialogBox'
import { copyText } from '../composables/clipboard'

const props = defineProps({
  selfUid: { type: Number, required: true },
})

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()
const dialogBox = useDialogBox()

// 悬浮框开关
const showUserPanel = ref(false)
const showExamPanel = ref(false)
const showExamConfigPanel = ref(false)
const showAnswerSheet = ref(false)
const showFeedbackPanel = ref(false)

// ------------------------------------------------------------------
// 用户管理（原表格逻辑迁入悬浮框）
// ------------------------------------------------------------------
const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
// 进行中的行级操作（封禁/解锁/删答卷）：记录 uid，用于禁用按钮并显示圆环
const busyUid = ref(null)

// 权限对话框
const showDialog = ref(false)
const dialogUser = ref(null)
const permissionInput = ref('')
const dialogSaving = ref(false)

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

// 搜索（Item11）：输入 debounce 300ms；关键词变化后重置到第 1 页重新请求；空/空白 q 等同于不传
const userQuery = ref('')
const userQueryApplied = ref('')
let userSearchTimer = null

function applyUserSearch() {
  const next = userQuery.value.trim()
  if (next === userQueryApplied.value) return
  userQueryApplied.value = next
  page.value = 1
  fetchUsers()
}

function onUserSearchInput() {
  clearTimeout(userSearchTimer)
  userSearchTimer = setTimeout(applyUserSearch, 300)
}

function submitUserSearch() {
  clearTimeout(userSearchTimer)
  applyUserSearch()
}

async function fetchUsers() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      page_size: String(pageSize),
    })
    if (userQueryApplied.value) params.set('q', userQueryApplied.value)
    const res = await fetch(`/api/admin/users?${params.toString()}`, {
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      users.value = data.users || []
      total.value = data.total || 0
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  fetchUsers()
}

function viewUser(u) {
  router.push(`/user/${u.uid}`)
}

function isSelf(u) {
  return u.uid === props.selfUid
}

// 操作者自身权限（登录态 user 由 useAuth 公共变量提供）
const myPermission = computed(() => authState.user?.permission ?? 0)

// 与后端一致的两套权限判断（逻辑稍有差异）：
// - 封禁：只能封禁权限【严格低于自己】的用户（同级及以上不可封禁）
// - 改权限：可操作【同级 / 下级】，仅禁止操作权限高于自己的用户
function canBan(u) {
  return !isSelf(u) && myPermission.value > (u.permission ?? 0)
}

function canSetPermission(u) {
  return !isSelf(u) && myPermission.value >= (u.permission ?? 0)
}

async function toggleBan(u) {
  if (isSelf(u)) {
    showTip('warning', t('admin.cannotBanSelf'))
    return
  }
  if (!canBan(u)) {
    showTip('warning', t('admin.cannotManageHigher'))
    return
  }
  if (busyUid.value !== null) return
  const banned = !u.banned
  busyUid.value = u.uid
  try {
    const res = await fetch(`/api/user/${u.uid}/ban`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ banned }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      u.banned = !!data.banned
      showTip('info', banned ? t('admin.bannedDone') : t('admin.unbannedDone'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    busyUid.value = null
  }
}

async function unlock(u) {
  if (busyUid.value !== null) return
  busyUid.value = u.uid
  try {
    const res = await fetch(`/api/user/${u.uid}/unlock`, {
      method: 'POST',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      u.locked = false
      showTip('info', t('admin.unlockedDone'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    busyUid.value = null
  }
}

function openPermissionDialog(u) {
  if (isSelf(u)) {
    showTip('warning', t('admin.cannotChangeOwnPermission'))
    return
  }
  if (!canSetPermission(u)) {
    showTip('warning', t('admin.cannotManageHigher'))
    return
  }
  dialogUser.value = u
  permissionInput.value = String(u.permission)
  showDialog.value = true
}

function closeDialog() {
  showDialog.value = false
  dialogUser.value = null
  permissionInput.value = ''
}

async function submitPermission() {
  // v-model 对 number 输入框会返回数字，统一转字符串处理
  const raw = String(permissionInput.value ?? '').trim()
  if (raw === '') {
    showTip('error', t('admin.permissionInvalid'))
    return
  }
  const value = Number(raw)
  if (!Number.isInteger(value) || value < 0 || value > 4) {
    showTip('error', t('admin.permissionInvalid'))
    return
  }
  // 新权限值上限：不能设置得高于自己的权限（与后端 new_permission_higher 一致）
  if (value > myPermission.value) {
    showTip('warning', t('admin.newPermissionHigher'))
    return
  }
  dialogSaving.value = true
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 8000)
  try {
    const res = await fetch(`/api/user/${dialogUser.value.uid}/permission`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ permission: value }),
      signal: controller.signal,
    })
    clearTimeout(timer)
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      dialogUser.value.permission = data.permission
      showTip('info', t('admin.permissionDone'))
      closeDialog()
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    clearTimeout(timer)
    dialogSaving.value = false
  }
}

async function onCopyUid(u) {
  const ok = await copyText(String(u.uid))
  if (ok) showTip('info', t('user.copiedUid'))
  else showTip('error', t('user.copyFailed'))
}

function avatarSrc(u) {
  return u.avatar ? `/api/user/${u.uid}/avatar` : ''
}

// ------------------------------------------------------------------
// 考试管理
// ------------------------------------------------------------------
const candidates = ref([])
const cTotal = ref(0)
const cPage = ref(1)
const cPageSize = 10
const cLoading = ref(false)
const cTotalPages = computed(() => Math.max(1, Math.ceil(cTotal.value / cPageSize)))

// 搜索（Item11）：同上，debounce 300ms + 重置第 1 页；q 走 /api/admin/exam/candidates
const cQuery = ref('')
const cQueryApplied = ref('')
let candidateSearchTimer = null

function applyCandidateSearch() {
  const next = cQuery.value.trim()
  if (next === cQueryApplied.value) return
  cQueryApplied.value = next
  cPage.value = 1
  fetchCandidates()
}

function onCandidateSearchInput() {
  clearTimeout(candidateSearchTimer)
  candidateSearchTimer = setTimeout(applyCandidateSearch, 300)
}

function submitCandidateSearch() {
  clearTimeout(candidateSearchTimer)
  applyCandidateSearch()
}

async function fetchCandidates() {
  cLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(cPage.value),
      page_size: String(cPageSize),
    })
    if (cQueryApplied.value) params.set('q', cQueryApplied.value)
    const res = await fetch(
      `/api/admin/exam/candidates?${params.toString()}`,
      { headers: authHeaders() }
    )
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      candidates.value = data.candidates || []
      cTotal.value = data.total || 0
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    cLoading.value = false
  }
}

function cGoPage(p) {
  if (p < 1 || p > cTotalPages.value) return
  cPage.value = p
  fetchCandidates()
}

async function deleteAnswers(c) {
  if (busyUid.value !== null) return
  busyUid.value = c.uid
  try {
    const res = await fetch(`/api/admin/exam/answers/${c.uid}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('admin.examDeleted'))
      fetchCandidates()
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    busyUid.value = null
  }
}

// ------------------------------------------------------------------
// 答题卡审阅
// ------------------------------------------------------------------
const sheet = ref(null)
const sheetLoading = ref(false)

async function openAnswerSheet(c) {
  showAnswerSheet.value = true
  sheetLoading.value = true
  sheet.value = null
  try {
    const res = await fetch(`/api/admin/exam/answers/${c.uid}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      sheet.value = data
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    sheetLoading.value = false
  }
}

const sheetQuestionIds = computed(() => {
  if (!sheet.value) return []
  return Object.keys(sheet.value.answers)
    .map(Number)
    .sort((a, b) => a - b)
})

function onSheetScoreSaved(payload) {
  // 刷新总分与通过状态
  if (!sheet.value) return
  const answered = sheet.value.answers
  sheet.value.obtained_score = sheetQuestionIds.value.reduce(
    (sum, qid) => sum + (answered[qid].obtained_score || 0),
    0
  )
  if (payload && typeof payload.passed === 'boolean') {
    sheet.value.profile = { ...(sheet.value.profile || {}), passed: payload.passed }
  }
}

// ------------------------------------------------------------------
// 反馈管理
// ------------------------------------------------------------------
const feedbackItems = ref([])
const feedbackTotal = ref(0)
const feedbackPage = ref(1)
const feedbackPageSize = 10
const feedbackStatusFilter = ref('')
const feedbackLoading = ref(false)
const feedbackBusyId = ref(null)
const feedbackTotalPages = computed(() =>
  Math.max(1, Math.ceil(feedbackTotal.value / feedbackPageSize))
)

const FEEDBACK_STATUSES = ['pending', 'resolved', 'closed']

const feedbackStatusOptions = computed(() => [
  { value: '', label: t('admin.feedbackStatusAll') },
  ...FEEDBACK_STATUSES.map((s) => ({ value: s, label: feedbackStatusLabel(s) })),
])

const feedbackRowStatusOptions = computed(() =>
  FEEDBACK_STATUSES.map((s) => ({ value: s, label: feedbackStatusLabel(s) }))
)

function feedbackCategoryLabel(category) {
  const key = `feedback.category${category.charAt(0).toUpperCase()}${category.slice(1)}`
  return t(key)
}

function feedbackStatusLabel(status) {
  const key = `feedback.status${status.charAt(0).toUpperCase()}${status.slice(1)}`
  return t(key)
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 搜索（Item11）：复用公开反馈列表已支持的 q 参数（标题/内容关键词），debounce 300ms + 重置第 1 页
const feedbackQuery = ref('')
const feedbackQueryApplied = ref('')
let feedbackSearchTimer = null

function applyFeedbackSearch() {
  const next = feedbackQuery.value.trim()
  if (next === feedbackQueryApplied.value) return
  feedbackQueryApplied.value = next
  feedbackPage.value = 1
  fetchFeedbacks()
}

function onFeedbackSearchInput() {
  clearTimeout(feedbackSearchTimer)
  feedbackSearchTimer = setTimeout(applyFeedbackSearch, 300)
}

function submitFeedbackSearch() {
  clearTimeout(feedbackSearchTimer)
  applyFeedbackSearch()
}

async function fetchFeedbacks() {
  feedbackLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(feedbackPage.value),
      page_size: String(feedbackPageSize),
      status: feedbackStatusFilter.value,
    })
    if (feedbackQueryApplied.value) params.set('q', feedbackQueryApplied.value)
    const res = await fetch(`/api/feedback?${params.toString()}`)
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      feedbackItems.value = data.items || []
      feedbackTotal.value = data.total || 0
      if (feedbackPage.value > feedbackTotalPages.value && feedbackTotalPages.value >= 1) {
        feedbackPage.value = feedbackTotalPages.value
        await fetchFeedbacks()
      }
    } else {
      feedbackItems.value = []
      feedbackTotal.value = 0
    }
  } catch (e) {
    feedbackItems.value = []
    feedbackTotal.value = 0
    console.warn(e)
  } finally {
    feedbackLoading.value = false
  }
}

function openFeedbackPanel() {
  showFeedbackPanel.value = true
  fetchFeedbacks()
}

function onFeedbackFilterChange() {
  feedbackPage.value = 1
  fetchFeedbacks()
}

function feedbackGoPage(target) {
  const next = Math.min(Math.max(1, target), feedbackTotalPages.value)
  if (next === feedbackPage.value) return
  feedbackPage.value = next
  fetchFeedbacks()
}

async function changeFeedbackStatus(item, status) {
  if (feedbackBusyId.value !== null) return
  feedbackBusyId.value = item.id
  try {
    const res = await fetch(`/api/admin/feedback/${item.id}/status`, {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ status }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      item.status = status
      showTip('info', t('admin.feedbackStatusUpdated'))
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    feedbackBusyId.value = null
  }
}

async function deleteFeedbackItem(item) {
  const ok = await dialogBox.confirm({
    title: t('feedback.deleteConfirmTitle'),
    message: t('admin.feedbackDeleteConfirm'),
    danger: true,
  })
  if (!ok) return
  try {
    const res = await fetch(`/api/feedback/${item.id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('admin.feedbackDeleteSuccess'))
      fetchFeedbacks()
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  }
}

function viewFeedback(item) {
  router.push(`/feedback/${item.id}`)
}

// ESC：依次关闭答题卡 / 反馈管理 / 试卷管理 / 考试管理 / 用户管理
function handleKeydown(e) {
  if (e.key !== 'Escape') return
  if (showAnswerSheet.value) showAnswerSheet.value = false
  else if (showFeedbackPanel.value) showFeedbackPanel.value = false
  else if (showExamConfigPanel.value) showExamConfigPanel.value = false
  else if (showExamPanel.value) showExamPanel.value = false
  else if (showUserPanel.value) showUserPanel.value = false
  else if (showDialog.value) closeDialog()
}

function openUserPanel() {
  showUserPanel.value = true
  if (users.value.length === 0) fetchUsers()
}

function openExamPanel() {
  showExamPanel.value = true
  if (candidates.value.length === 0) fetchCandidates()
}

function openExamConfigPanel() {
  showExamConfigPanel.value = true
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  clearTimeout(userSearchTimer)
  clearTimeout(candidateSearchTimer)
  clearTimeout(feedbackSearchTimer)
})
</script>

<template>
  <section class="admin-settings">
    <!-- 四个管理入口 -->
    <div class="entry-row load-in">
      <button type="button" class="entry-card" @click="openUserPanel">
        <Users :size="26" />
        <span class="entry-title">{{ t('admin.userEntry') }}</span>
        <span class="entry-desc">{{ t('admin.userEntryDesc') }}</span>
      </button>
      <button type="button" class="entry-card" @click="openExamPanel">
        <FileText :size="26" />
        <span class="entry-title">{{ t('admin.examEntry') }}</span>
        <span class="entry-desc">{{ t('admin.examEntryDesc') }}</span>
      </button>
      <button type="button" class="entry-card" @click="openExamConfigPanel">
        <BookOpen :size="26" />
        <span class="entry-title">{{ t('admin.examConfigEntry') }}</span>
        <span class="entry-desc">{{ t('admin.examConfigEntryDesc') }}</span>
      </button>
      <button type="button" class="entry-card" @click="openFeedbackPanel">
        <MessageSquare :size="26" />
        <span class="entry-title">{{ t('admin.feedbackEntry') }}</span>
        <span class="entry-desc">{{ t('admin.feedbackEntryDesc') }}</span>
      </button>
    </div>

    <!-- 用户管理悬浮框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showUserPanel" class="panel-overlay">
          <div class="panel">
            <header class="panel-head">
              <h2 class="panel-title">{{ t('admin.userEntry') }}</h2>
              <div class="panel-head-tools">
                <div class="panel-search">
                  <Search :size="15" class="panel-search-icon" />
                  <input
                    v-model="userQuery"
                    type="text"
                    class="panel-search-input"
                    :placeholder="t('admin.searchUser')"
                    :aria-label="t('admin.searchUser')"
                    @input="onUserSearchInput"
                    @keydown.enter="submitUserSearch"
                  />
                </div>
                <button type="button" class="panel-close" :aria-label="t('message.close')" @click="showUserPanel = false">
                  <X :size="18" />
                </button>
              </div>
            </header>

            <div class="panel-body">
              <div v-if="loading" class="table-empty"><span class="spinner"></span>{{ t('admin.loading') }}</div>
              <div v-else-if="users.length === 0" class="table-empty">{{ t('admin.noUsers') }}</div>
              <div v-else class="table-scroll">
                <table class="user-table">
                  <thead>
                    <tr>
                      <th>{{ t('admin.user') }}</th>
                      <th class="th-actions">{{ t('admin.actions') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="u in users" :key="u.uid">
                      <td>
                        <div class="user-cell">
                          <img v-if="avatarSrc(u)" :src="avatarSrc(u)" class="cell-avatar" alt="avatar" />
                          <span v-else class="cell-avatar cell-avatar-fallback"><UserRound :size="20" /></span>
                          <div class="cell-names">
                            <span class="cell-username">{{ u.username }}</span>
                            <span class="cell-uid" :title="t('user.copiedUid')" @click="onCopyUid(u)">UID: {{ u.uid }}</span>
                          </div>
                          <span v-if="u.banned" class="badge banned">{{ t('admin.banned') }}</span>
                          <span v-if="u.locked" class="badge locked">{{ t('admin.locked') }}</span>
                        </div>
                      </td>
                      <td>
                        <div class="row-actions">
                          <button class="icon-btn" :disabled="busyUid !== null" :title="t('admin.view')" :aria-label="t('admin.view')" @click="viewUser(u)">
                            <Eye :size="18" />
                          </button>
                          <button
                            class="icon-btn"
                            :class="{ danger: !u.banned, success: u.banned }"
                            :disabled="!canBan(u) || busyUid !== null"
                            :title="canBan(u) ? (u.banned ? t('admin.unban') : t('admin.ban')) : t('admin.cannotManageHigher')"
                            :aria-label="canBan(u) ? (u.banned ? t('admin.unban') : t('admin.ban')) : t('admin.cannotManageHigher')"
                            @click="toggleBan(u)"
                          >
                            <span v-if="busyUid === u.uid" class="spinner"></span>
                            <CircleCheck v-else-if="u.banned" :size="18" />
                            <Ban v-else :size="18" />
                          </button>
                          <button
                            class="icon-btn"
                            :disabled="!canSetPermission(u) || busyUid !== null"
                            :title="canSetPermission(u) ? t('admin.setPermission') : t('admin.cannotManageHigher')"
                            :aria-label="canSetPermission(u) ? t('admin.setPermission') : t('admin.cannotManageHigher')"
                            @click="openPermissionDialog(u)"
                          >
                            <Shield :size="18" />
                          </button>
                          <button
                            v-if="u.locked"
                            class="icon-btn"
                            :disabled="busyUid !== null"
                            :title="t('admin.unlock')"
                            :aria-label="t('admin.unlock')"
                            @click="unlock(u)"
                          >
                            <span v-if="busyUid === u.uid" class="spinner"></span>
                            <LockOpen v-else :size="18" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="pagination">
                <button class="page-btn" :disabled="page <= 1 || loading" @click="goPage(page - 1)">
                  <span v-if="loading" class="spinner"></span>
                  <ChevronLeft v-else :size="18" />
                </button>
                <span class="page-info">{{ t('admin.pageInfo', { page, total: totalPages }) }}</span>
                <button class="page-btn" :disabled="page >= totalPages || loading" @click="goPage(page + 1)">
                  <span v-if="loading" class="spinner"></span>
                  <ChevronRight v-else :size="18" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 考试管理悬浮框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showExamPanel" class="panel-overlay">
          <div class="panel">
            <header class="panel-head">
              <h2 class="panel-title">{{ t('admin.examEntry') }}</h2>
              <div class="panel-head-tools">
                <div class="panel-search">
                  <Search :size="15" class="panel-search-icon" />
                  <input
                    v-model="cQuery"
                    type="text"
                    class="panel-search-input"
                    :placeholder="t('admin.searchCandidate')"
                    :aria-label="t('admin.searchCandidate')"
                    @input="onCandidateSearchInput"
                    @keydown.enter="submitCandidateSearch"
                  />
                </div>
                <button type="button" class="panel-close" :aria-label="t('message.close')" @click="showExamPanel = false">
                  <X :size="18" />
                </button>
              </div>
            </header>

            <div class="panel-body">
              <div v-if="cLoading" class="table-empty"><span class="spinner"></span>{{ t('admin.loading') }}</div>
              <div v-else-if="candidates.length === 0" class="table-empty">{{ t('admin.examNoCandidates') }}</div>
              <div v-else class="table-scroll">
                <table class="user-table">
                  <thead>
                    <tr>
                      <th>{{ t('admin.user') }}</th>
                      <th class="th-actions">{{ t('admin.actions') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="c in candidates" :key="c.uid">
                      <td>
                        <div class="user-cell">
                          <img v-if="c.avatar" :src="`/api/user/${c.uid}/avatar`" class="cell-avatar" alt="avatar" />
                          <span v-else class="cell-avatar cell-avatar-fallback"><UserRound :size="20" /></span>
                          <div class="cell-names">
                            <span class="cell-username">{{ c.username }}<span v-if="c.player_name" class="pname"> · {{ c.player_name }}</span></span>
                            <span class="cell-uid">UID: {{ c.uid }} · {{ t('admin.examAttempts', { n: c.attempts }) }} · {{ c.passed ? t('admin.examPassed') : t('admin.examNotPassed') }}</span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div class="row-actions">
                          <button class="icon-btn" :disabled="busyUid !== null" :title="t('admin.examViewSheet')" :aria-label="t('admin.examViewSheet')" @click="openAnswerSheet(c)">
                            <FileText :size="18" />
                          </button>
                          <button class="icon-btn danger" :disabled="busyUid !== null" :title="t('admin.examDelete')" :aria-label="t('admin.examDelete')" @click="deleteAnswers(c)">
                            <span v-if="busyUid === c.uid" class="spinner"></span>
                            <Trash2 v-else :size="18" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="pagination">
                <button class="page-btn" :disabled="cPage <= 1 || cLoading" @click="cGoPage(cPage - 1)">
                  <span v-if="cLoading" class="spinner"></span>
                  <ChevronLeft v-else :size="18" />
                </button>
                <span class="page-info">{{ t('admin.pageInfo', { page: cPage, total: cTotalPages }) }}</span>
                <button class="page-btn" :disabled="cPage >= cTotalPages || cLoading" @click="cGoPage(cPage + 1)">
                  <span v-if="cLoading" class="spinner"></span>
                  <ChevronRight v-else :size="18" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 答题卡审阅悬浮框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showAnswerSheet" class="panel-overlay">
          <div class="panel panel-wide">
            <header class="panel-head">
              <h2 class="panel-title">{{ t('admin.examSheetTitle') }}</h2>
              <button type="button" class="panel-close" :aria-label="t('message.close')" @click="showAnswerSheet = false">
                <X :size="18" />
              </button>
            </header>

            <div class="panel-body">
              <div v-if="sheetLoading" class="table-empty"><span class="spinner"></span>{{ t('admin.loading') }}</div>
              <template v-else-if="sheet">
                <div class="sheet-meta">
                  <span class="meta-left">
                    {{ t('admin.examTotalScore', { obtained: sheet.obtained_score, total: sheet.total_score }) }}
                    <span v-if="sheet.profile && sheet.profile.passed" class="sheet-passed">{{ t('admin.examPassed') }}</span>
                  </span>
                  <span v-if="sheet.profile" class="sheet-profile">
                    {{ sheet.profile.player_name || '' }}
                  </span>
                </div>
                <div class="sheet-list">
                  <ExamQuestion
                    v-for="qid in sheetQuestionIds"
                    :key="qid"
                    :question="sheet.answers[qid].question"
                    :model-value="sheet.answers[qid].answer"
                    :mode="'review'"
                    :review-uid="sheet.uid"
                    :review-score="sheet.answers[qid].obtained_score"
                    :review-attachment="sheet.answers[qid].attachment || []"
                    @score-saved="onSheetScoreSaved"
                  />
                </div>
              </template>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 试卷管理悬浮框（在线编辑考试试卷） -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showExamConfigPanel" class="panel-overlay">
          <div class="panel panel-wide">
            <header class="panel-head">
              <h2 class="panel-title">{{ t('admin.examConfigEntry') }}</h2>
              <button type="button" class="panel-close" :aria-label="t('message.close')" @click="showExamConfigPanel = false">
                <X :size="18" />
              </button>
            </header>
            <div class="panel-body">
              <ExamEditor />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 反馈管理悬浮框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showFeedbackPanel" class="panel-overlay">
          <div class="panel panel-wide">
            <header class="panel-head">
              <h2 class="panel-title">{{ t('admin.feedbackEntry') }}</h2>
              <div class="panel-head-tools">
                <div class="panel-search">
                  <Search :size="15" class="panel-search-icon" />
                  <input
                    v-model="feedbackQuery"
                    type="text"
                    class="panel-search-input"
                    :placeholder="t('admin.feedbackSearchPlaceholder')"
                    :aria-label="t('admin.feedbackSearchPlaceholder')"
                    @input="onFeedbackSearchInput"
                    @keydown.enter="submitFeedbackSearch"
                  />
                </div>
                <StatusDropdown
                  v-model="feedbackStatusFilter"
                  :options="feedbackStatusOptions"
                  class="panel-filter"
                  :aria-label="t('feedback.filterStatus')"
                  @update:model-value="onFeedbackFilterChange"
                />
                <button type="button" class="panel-close" :aria-label="t('message.close')" @click="showFeedbackPanel = false">
                  <X :size="18" />
                </button>
              </div>
            </header>

            <div class="panel-body">
              <div v-if="feedbackLoading" class="table-empty"><span class="spinner"></span>{{ t('admin.loading') }}</div>
              <div v-else-if="!feedbackItems.length" class="table-empty">{{ t('admin.feedbackEmpty') }}</div>
              <template v-else>
                <div class="table-scroll">
                  <table class="user-table feedback-table">
                    <thead>
                      <tr>
                        <th>{{ t('feedback.titleLabel') }}</th>
                        <th>{{ t('feedback.author') }}</th>
                        <th>{{ t('feedback.statusLabel') }}</th>
                        <th>{{ t('feedback.updatedAt') }}</th>
                        <th class="th-actions">{{ t('admin.actions') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in feedbackItems" :key="item.id">
                        <td>
                          <div class="fb-title-cell">
                            <button type="button" class="fb-feedback-title" :title="item.title" @click="viewFeedback(item)">
                              {{ item.title }}
                            </button>
                            <span class="fb-cat-chip">{{ feedbackCategoryLabel(item.category) }}</span>
                          </div>
                        </td>
                        <td class="fb-feedback-author">{{ item.author_name || t('feedback.anonymous') }}</td>
                        <td>
                          <StatusDropdown
                            :model-value="item.status"
                            :options="feedbackRowStatusOptions"
                            variant="chip"
                            :disabled="feedbackBusyId === item.id"
                            :aria-label="t('feedback.statusLabel')"
                            @update:model-value="(status) => changeFeedbackStatus(item, status)"
                          />
                        </td>
                        <td class="fb-feedback-time">{{ formatTime(item.updated_at) }}</td>
                        <td>
                          <div class="row-actions">
                            <button class="icon-btn" :title="t('admin.feedbackView')" :aria-label="t('admin.feedbackView')" @click="viewFeedback(item)">
                              <Eye :size="18" />
                            </button>
                            <button class="icon-btn danger" :title="t('admin.feedbackDelete')" :aria-label="t('admin.feedbackDelete')" @click="deleteFeedbackItem(item)">
                              <Trash2 :size="18" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="pagination">
                  <button class="page-btn" :disabled="feedbackPage <= 1 || feedbackLoading" @click="feedbackGoPage(feedbackPage - 1)">
                    <ChevronLeft :size="18" />
                  </button>
                  <span class="page-info">{{ t('admin.pageInfo', { page: feedbackPage, total: feedbackTotalPages }) }}</span>
                  <button class="page-btn" :disabled="feedbackPage >= feedbackTotalPages || feedbackLoading" @click="feedbackGoPage(feedbackPage + 1)">
                    <ChevronRight :size="18" />
                  </button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 权限设置对话框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showDialog" class="panel-overlay">
          <div class="mini-dialog">
            <h3 class="dialog-title">{{ t('admin.setPermission') }}</h3>
            <p class="dialog-hint">{{ dialogUser ? dialogUser.username : '' }} · UID {{ dialogUser ? dialogUser.uid : '' }}</p>
            <input
              v-model="permissionInput"
              type="number"
              min="0"
              max="4"
              class="dialog-input"
              :placeholder="t('admin.permissionInvalid')"
            />
            <div class="dialog-actions">
              <button class="btn cancel" :disabled="dialogSaving" @click="closeDialog">{{ t('admin.cancel') }}</button>
              <button class="btn primary" :disabled="dialogSaving" @click="submitPermission">
                <span v-if="dialogSaving" class="spinner"></span>
                {{ t('admin.set') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </section>
</template>

<style scoped>
.admin-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.entry-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.entry-card {
  flex: 1;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 24px;
  border-radius: 20px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  color: var(--text-color);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s ease, transform 0.15s ease;
}

.entry-card:hover {
  border-color: var(--text-color);
  transform: translateY(-2px);
}

.entry-title {
  font-size: 18px;
  font-weight: 700;
}

.entry-desc {
  font-size: 13px;
  color: var(--links-color);
}

/* 悬浮框 */
.panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 9500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.5);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}

.panel {
  width: min(760px, 100%);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  color: var(--text-color);
  overflow: hidden;
}

.panel-wide {
  width: min(860px, 100%);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* 标题 + 工具区（搜索 / 状态筛选 / 关闭）：窄屏换行，不溢出、不遮挡 */
  flex-wrap: wrap;
  gap: 10px 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--links-color);
}

.panel-title {
  margin: 0;
  flex-shrink: 0;
  font-size: 18px;
  font-weight: 700;
}

.panel-head-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex: 1 1 auto;
  min-width: 0;
}

/* 面板头部搜索框（用户 / 考试 / 反馈管理共用，含 Search 图标） */
.panel-search {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1 1 160px;
  max-width: 260px;
  height: 36px;
  min-width: 0;
  padding: 0 12px;
  box-sizing: border-box;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 999px;
  background: var(--card-color);
  color: var(--links-color);
  transition: border-color 0.15s ease;
}

.panel-search:focus-within {
  border-color: var(--text-color);
}

.panel-search-icon {
  flex-shrink: 0;
}

.panel-search-input {
  flex: 1;
  min-width: 0;
  width: 100%;
  padding: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 13.5px;
}

.panel-search-input::placeholder {
  color: var(--links-color);
}

/* 头部内的状态筛选：高度与搜索框对齐（行内 chip 样式不变） */
.panel-head-tools .panel-filter {
  flex-shrink: 0;
}

.panel-head .panel-head-tools :deep(.sd-pill .sd-btn) {
  height: 36px;
  padding: 0 14px;
  font-size: 13px;
}

.panel-close {
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
}

.panel-close:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.panel-body {
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow-y: auto;
}

.table-empty {
  padding: 32px 0;
  text-align: center;
  color: var(--links-color);
}

.table-scroll {
  overflow-x: auto;
}

.user-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 520px;
}

.user-table th {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  color: var(--links-color);
  font-size: 13px;
  font-weight: 600;
}

.th-actions {
  text-align: right !important;
}

.user-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  vertical-align: middle;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cell-avatar {
  width: 40px;
  height: 40px;
  border-radius: 999px;
  object-fit: cover;
  flex-shrink: 0;
}

.cell-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--float-bg);
  color: var(--links-color);
}

.cell-names {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.cell-username {
  font-weight: 600;
  color: var(--text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pname {
  color: var(--links-color);
  font-weight: 400;
}

.cell-uid {
  font-size: 12px;
  color: var(--links-color);
  cursor: pointer;
}

.cell-uid:hover {
  color: var(--text-color);
}

.badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  flex-shrink: 0;
}

.badge.banned {
  background: rgba(229, 72, 77, 0.15);
  color: #e5484d;
}

.badge.locked {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.icon-btn:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.icon-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.icon-btn:disabled:hover {
  background: transparent;
  color: var(--links-color);
}

.icon-btn.danger {
  color: #e5484d;
}

.icon-btn.success {
  color: #2e9e5b;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
}

.page-btn:hover:not(:disabled) {
  background: var(--float-bg);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 14px;
  color: var(--links-color);
}

/* 答题卡 */
.sheet-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-bottom: 14px;
  border-radius: 12px;
  background: var(--float-bg);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
}

.meta-left {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.sheet-passed {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  background: rgba(46, 158, 91, 0.15);
  color: #2e9e5b;
}

.sheet-profile {
  color: var(--links-color);
  font-weight: 400;
}

.sheet-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 权限对话框 */
.mini-dialog {
  width: min(360px, 100%);
  padding: 24px;
  border-radius: 16px;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  color: var(--text-color);
}

.dialog-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
}

.dialog-hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--links-color);
}

.dialog-input {
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

.dialog-actions {
  display: flex;
  justify-content: flex-start;
  gap: 10px;
  margin-top: 16px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.btn.cancel {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
/* 反馈管理：表格布局优化（标题最多两行、分类 chip 不换行、行距更宽松） */
.feedback-table {
  min-width: 620px;
}

.feedback-table th,
.feedback-table td {
  padding: 12px;
}

/* 表头不折行（如「作者」列较窄时不会竖排），列宽由内容自动布局 */
.feedback-table th {
  white-space: nowrap;
}

.feedback-table .fb-title-cell {
  min-width: 200px;
}

.feedback-table .fb-feedback-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  max-width: 100%;
  white-space: normal;
  overflow: hidden;
  line-height: 1.45;
}

.feedback-table .fb-cat-chip {
  white-space: nowrap;
}

.fb-title-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
}

.fb-cat-chip {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--float-bg);
  color: var(--links-color);
  font-size: 11px;
  font-weight: 600;
}

.fb-feedback-title {
  display: block;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0;
  border: none;
  background: none;
  color: var(--text-color);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.fb-feedback-title:hover {
  color: var(--notice-color);
}

.fb-feedback-author,
.fb-feedback-time {
  color: var(--links-color);
  font-size: 12.5px;
  white-space: nowrap;
}

/* 手机端：面板头部换行排列（标题一行，搜索框 / 状态筛选 / 关闭按钮一行），
   搜索框可收缩，不溢出、不遮挡内容 */
@media (max-width: 768px) {
  .panel-head-tools {
    flex: 1 1 100%;
    flex-wrap: wrap;
  }

  .panel-search {
    flex: 1 1 130px;
    max-width: none;
  }

  /* 覆盖 status_dropdown 在手机端「整行宽度」的默认样式，保持与搜索框同一行 */
  .panel-head .panel-head-tools :deep(.sd-pill),
  .panel-head .panel-head-tools :deep(.sd-pill .sd-btn) {
    width: auto;
  }
}
</style>

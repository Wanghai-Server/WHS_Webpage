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
  X,
} from 'lucide-vue-next'
import ExamQuestion from './exam_question.vue'
import ExamEditor from './exam_editor.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { copyText } from '../composables/clipboard'

const props = defineProps({
  selfUid: { type: Number, required: true },
})

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()

// 悬浮框开关
const showUserPanel = ref(false)
const showExamPanel = ref(false)
const showExamConfigPanel = ref(false)
const showAnswerSheet = ref(false)

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

async function fetchUsers() {
  loading.value = true
  try {
    const res = await fetch(`/api/admin/users?page=${page.value}&page_size=${pageSize}`, {
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

async function fetchCandidates() {
  cLoading.value = true
  try {
    const res = await fetch(
      `/api/admin/exam/candidates?page=${cPage.value}&page_size=${cPageSize}`,
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

// ESC：依次关闭答题卡 / 试卷管理 / 考试管理 / 用户管理
function handleKeydown(e) {
  if (e.key !== 'Escape') return
  if (showAnswerSheet.value) showAnswerSheet.value = false
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
})
</script>

<template>
  <section class="admin-settings">
    <!-- 三个管理入口 -->
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
    </div>

    <!-- 用户管理悬浮框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showUserPanel" class="panel-overlay" @click.self="showUserPanel = false">
          <div class="panel">
            <header class="panel-head">
              <h2 class="panel-title">{{ t('admin.userEntry') }}</h2>
              <button type="button" class="panel-close" :aria-label="t('message.close')" @click="showUserPanel = false">
                <X :size="18" />
              </button>
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
        <div v-if="showExamPanel" class="panel-overlay" @click.self="showExamPanel = false">
          <div class="panel">
            <header class="panel-head">
              <h2 class="panel-title">{{ t('admin.examEntry') }}</h2>
              <button type="button" class="panel-close" :aria-label="t('message.close')" @click="showExamPanel = false">
                <X :size="18" />
              </button>
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
        <div v-if="showAnswerSheet" class="panel-overlay" @click.self="showAnswerSheet = false">
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
        <div v-if="showExamConfigPanel" class="panel-overlay" @click.self="showExamConfigPanel = false">
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

    <!-- 权限设置对话框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showDialog" class="panel-overlay" @click.self="closeDialog">
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
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.panel {
  width: min(760px, 100%);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
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
  padding: 16px 20px;
  border-bottom: 1px solid var(--links-color);
}

.panel-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
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
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
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
</style>

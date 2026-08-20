<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban, FileText, LockOpen, X } from 'lucide-vue-next'
import ExamQuestion from './exam_question.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

// 管理员在【他人】用户页看到的"管理员"分页：
// 只提供三个操作 —— 封禁/解禁、查看答题卡、解锁账号（仅账号被锁定时展示）。
// 与自身页面的 AdminSettings（用户管理/考试管理/试卷管理）不同。
const props = defineProps({
  user: { type: Object, required: true }, // /api/user/{uid} 返回的用户数据（含 permission/locked/banned）
})

const emit = defineEmits(['changed'])

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

// 操作者自身权限（登录态 user 由 useAuth 公共变量提供）
const myPermission = computed(() => authState.user?.permission ?? 0)
const targetPermission = computed(() => props.user.permission ?? 0)
// 与后端一致：封禁 / 解锁只能操作权限【严格低于自己】的用户（同级及以上不可操作）
const canManage = computed(() => myPermission.value > targetPermission.value)

const busy = ref(false)

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

// ------------------------------------------------------------------
// 1. 封禁 / 解禁
// ------------------------------------------------------------------
async function toggleBan() {
  if (!canManage.value) {
    showTip('warning', t('admin.cannotManageHigher'))
    return
  }
  if (busy.value) return
  const banned = !props.user.banned
  busy.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/ban`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ banned }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', banned ? t('admin.bannedDone') : t('admin.unbannedDone'))
      emit('changed')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    busy.value = false
  }
}

// ------------------------------------------------------------------
// 2. 解锁账号（仅账号锁定时展示按钮）
// ------------------------------------------------------------------
async function unlock() {
  if (!canManage.value) {
    showTip('warning', t('admin.cannotManageHigher'))
    return
  }
  if (busy.value) return
  busy.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/unlock`, {
      method: 'POST',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('admin.unlockedDone'))
      emit('changed')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    busy.value = false
  }
}

// ------------------------------------------------------------------
// 3. 查看答题卡（复用 ExamQuestion 审阅模式，可改分）
// ------------------------------------------------------------------
const showSheet = ref(false)
const sheetLoading = ref(false)
const sheet = ref(null)
const sheetQuestionIds = computed(() =>
  sheet.value ? Object.keys(sheet.value.answers).map(Number).sort((a, b) => a - b) : []
)

async function fetchSheet() {
  sheetLoading.value = true
  try {
    const res = await fetch(`/api/admin/exam/answers/${props.user.uid}`, {
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      sheet.value = data
    } else {
      sheet.value = null
      showTip('error', localMessage(data))
    }
  } catch (e) {
    sheet.value = null
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    sheetLoading.value = false
  }
}

function openSheet() {
  showSheet.value = true
  sheet.value = null
  fetchSheet()
}

// 改分后静默刷新汇总（总分 / 及格状态）
function onSheetScoreSaved() {
  fetchSheet()
}

// Esc 关闭答题卡
function handleKeydown(e) {
  if (e.key === 'Escape' && showSheet.value) {
    showSheet.value = false
  }
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="admin-user-panel">
    <div class="admin-user-actions">
      <button type="button" class="action-btn" :disabled="busy" @click="toggleBan">
        <Ban :size="18" />
        {{ user.banned ? t('admin.unban') : t('admin.ban') }}
      </button>
      <button type="button" class="action-btn" :disabled="busy" @click="openSheet">
        <FileText :size="18" />
        {{ t('admin.examViewSheet') }}
      </button>
      <button v-if="user.locked" type="button" class="action-btn" :disabled="busy" @click="unlock">
        <LockOpen :size="18" />
        {{ t('admin.unlock') }}
      </button>
    </div>

    <!-- 答题卡审阅悬浮框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showSheet" class="sheet-overlay" @click.self="showSheet = false">
          <div class="sheet-modal dialog">
            <header class="sheet-head">
              <h3>{{ t('admin.examSheetTitle') }}</h3>
              <button type="button" class="sheet-close" :aria-label="t('message.close')" @click="showSheet = false">
                <X :size="18" />
              </button>
            </header>

            <div class="sheet-body">
              <div v-if="sheetLoading" class="sheet-empty"><span class="spinner"></span>{{ t('admin.loading') }}</div>
              <template v-else-if="sheet">
                <div class="sheet-meta">
                  <span>
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
  </div>
</template>

<style scoped>
.admin-user-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 22px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease,
    opacity 0.2s ease;
}

.action-btn:hover:not(:disabled) {
  border-color: rgba(235, 170, 40, 0.5);
  background: rgba(235, 170, 40, 0.08);
}

.action-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

/* 答题卡悬浮窗 */
.sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.sheet-modal {
  width: min(880px, 100%);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.3);
}

.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.sheet-head h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-color);
}

.sheet-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
}

.sheet-close:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.sheet-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.sheet-empty {
  padding: 60px 0;
  text-align: center;
  color: var(--links-color);
}

.sheet-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  font-size: 14px;
  color: var(--text-color);
}

.sheet-passed {
  margin-left: 8px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  font-size: 12px;
  font-weight: 700;
}

.sheet-profile {
  font-size: 13px;
  color: var(--links-color);
}

.sheet-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>

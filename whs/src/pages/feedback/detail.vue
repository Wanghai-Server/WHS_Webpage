<script setup>
/**
 * 反馈详情页（/feedback/:id）。
 *
 * - 展示反馈标题、分类、状态、作者、时间与 Markdown 正文；
 * - 作者可编辑 / 删除；管理员可修改状态、删除；
 * - 评论区：登录用户可发表 Markdown 评论。
 */
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft,
  Pencil,
  Trash2,
  MessageSquare,
  UserRound,
} from 'lucide-vue-next'
import Top_navbar from '../../components/top_navbar.vue'
import Page_footer from '../../components/page_footer.vue'
import WikiMarkdown from '../../components/wiki/wiki_markdown.vue'
import FeedbackEditor from '../../components/feedback_editor.vue'
import StatusDropdown from '../../components/status_dropdown.vue'
import { useAuth } from '../../composables/useAuth'
import { useTips } from '../../composables/useTips'
import { useDialogBox } from '../../composables/useDialogBox'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()
const dialogBox = useDialogBox()

const loading = ref(true)
const notFound = ref(false)
const feedback = ref(null)
const comments = ref([])
const viewer = ref({ logged_in: false, can_edit: false, can_delete: false, can_moderate: false })
const editorOpen = ref(false)
const commentText = ref('')
const submittingComment = ref(false)
const statusUpdating = ref(false)

const isLoggedIn = computed(() => !!authState.token)

const STATUSES = ['pending', 'resolved', 'closed']

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

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function categoryLabel(category) {
  const key = `feedback.category${category.charAt(0).toUpperCase()}${category.slice(1)}`
  return t(key)
}

function statusLabel(status) {
  const key = `feedback.status${status.charAt(0).toUpperCase()}${status.slice(1)}`
  return t(key)
}

// 详情页状态下拉选项
const statusOptions = computed(() => STATUSES.map((s) => ({ value: s, label: statusLabel(s) })))

async function fetchDetail() {
  loading.value = true
  notFound.value = false
  try {
    const res = await fetch(`/api/feedback/${route.params.id}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      notFound.value = true
      feedback.value = null
      comments.value = []
      return
    }
    feedback.value = data.feedback
    comments.value = data.comments || []
    viewer.value = data.viewer || viewer.value
  } catch (e) {
    notFound.value = true
    console.warn(e)
  } finally {
    loading.value = false
  }
}

function back() {
  router.push('/feedback')
}

function openEdit() {
  editorOpen.value = true
}

function onSaved() {
  editorOpen.value = false
  fetchDetail()
}

async function deleteFeedback() {
  const ok = await dialogBox.confirm({
    title: t('feedback.deleteConfirmTitle'),
    message: t('feedback.deleteConfirmMessage'),
    danger: true,
  })
  if (!ok) return
  try {
    const res = await fetch(`/api/feedback/${feedback.value.id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('feedback.deleteSuccess'))
      router.push('/feedback')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  }
}

async function changeStatusTo(status) {
  if (statusUpdating.value) return
  statusUpdating.value = true
  try {
    const res = await fetch(`/api/admin/feedback/${feedback.value.id}/status`, {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ status }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      feedback.value.status = status
      showTip('info', t('feedback.statusChange'))
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    statusUpdating.value = false
  }
}

async function submitComment() {
  if (submittingComment.value) return
  if (!commentText.value.trim()) {
    showTip('warning', t('feedback.commentEmpty'))
    return
  }
  submittingComment.value = true
  try {
    const res = await fetch(`/api/feedback/${feedback.value.id}/comments`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ content: commentText.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      if (data.comment) comments.value.push(data.comment)
      commentText.value = ''
      showTip('info', t('feedback.commentSuccess'))
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    submittingComment.value = false
  }
}

function goLogin() {
  router.push('/login')
}

watch(() => route.params.id, fetchDetail, { immediate: true })
</script>

<template>
  <div class="fbd-page">
    <Top_navbar />

    <main class="fbd-main">
      <button type="button" class="fbd-back" @click="back">
        <ArrowLeft :size="16" />
        <span>{{ t('feedback.backToList') }}</span>
      </button>

      <div v-if="loading" class="fbd-state">
        <span class="spinner"></span>
      </div>
      <div v-else-if="notFound" class="fbd-state">
        {{ t('feedback.notFound') }}
      </div>

      <template v-else-if="feedback">
        <article class="fbd-card">
          <header class="fbd-head">
            <div class="fbd-head-main">
              <h1 class="fbd-title">{{ feedback.title }}</h1>
              <div class="fbd-meta">
                <span class="fbd-status" :class="`is-${feedback.status}`">{{ statusLabel(feedback.status) }}</span>
                <span class="fbd-badge">{{ categoryLabel(feedback.category) }}</span>
                <span class="fbd-meta-item">
                  <UserRound :size="14" />
                  <RouterLink
                    v-if="feedback.author_uid"
                    :to="`/user/${feedback.author_uid}`"
                    class="fbd-author"
                  >{{ feedback.author_name || t('feedback.anonymous') }}</RouterLink>
                  <span v-else>{{ feedback.author_name || t('feedback.anonymous') }}</span>
                </span>
                <span class="fbd-meta-item">
                  {{ t('feedback.createdAt') }} {{ formatTime(feedback.created_at) }}
                </span>
                <span v-if="feedback.updated_at && feedback.updated_at !== feedback.created_at" class="fbd-meta-item">
                  {{ t('feedback.updatedAt') }} {{ formatTime(feedback.updated_at) }}
                </span>
              </div>
            </div>

            <div v-if="viewer.logged_in" class="fbd-actions">
              <StatusDropdown
                v-if="viewer.can_moderate"
                class="fbd-status-select"
                :model-value="feedback.status"
                :options="statusOptions"
                variant="action"
                :aria-label="t('feedback.statusChange')"
                :disabled="statusUpdating"
                @update:model-value="changeStatusTo"
              />
              <button v-if="viewer.can_edit" type="button" class="fbd-action" @click="openEdit">
                <Pencil :size="15" />
                <span>{{ t('feedback.edit') }}</span>
              </button>
              <button v-if="viewer.can_delete" type="button" class="fbd-action danger" @click="deleteFeedback">
                <Trash2 :size="15" />
                <span>{{ t('feedback.delete') }}</span>
              </button>
            </div>
          </header>

          <div class="fbd-content">
            <WikiMarkdown :content="feedback.content" />
          </div>
        </article>

        <section class="fbd-comments">
          <h2 class="fbd-comments-title">
            <MessageSquare :size="18" />
            {{ t('feedback.comments') }}
            <span class="fbd-count">{{ comments.length }}</span>
          </h2>

          <p v-if="!comments.length" class="fbd-empty">{{ t('feedback.commentEmptyList') }}</p>
          <ul v-else class="fbd-comment-list">
            <li v-for="comment in comments" :key="comment.id" class="fbd-comment">
              <div class="fbd-comment-head">
                <span class="fbd-comment-author">
                  <RouterLink
                    v-if="comment.author_uid"
                    :to="`/user/${comment.author_uid}`"
                    class="fbd-author"
                  >{{ comment.author_name || t('feedback.anonymous') }}</RouterLink>
                  <span v-else>{{ comment.author_name || t('feedback.anonymous') }}</span>
                </span>
                <span class="fbd-comment-time">{{ formatTime(comment.created_at) }}</span>
              </div>
              <div class="fbd-comment-body">
                <WikiMarkdown :content="comment.content" />
              </div>
            </li>
          </ul>

          <div v-if="isLoggedIn" class="fbd-composer">
            <textarea
              v-model="commentText"
              class="fbd-comment-input"
              :placeholder="t('feedback.commentPlaceholder')"
              spellcheck="false"
            ></textarea>
            <div class="fbd-composer-actions">
              <button type="button" class="fbd-submit" :disabled="submittingComment" @click="submitComment">
                <span v-if="submittingComment" class="spinner"></span>
                {{ t('feedback.commentSubmit') }}
              </button>
            </div>
          </div>
          <div v-else class="fbd-login-hint">
            <span>{{ t('feedback.loginToComment') }}</span>
            <button type="button" class="fbd-login-btn" @click="goLogin">{{ t('feedback.loginNow') }}</button>
          </div>
        </section>
      </template>
    </main>

    <Page_footer />

    <FeedbackEditor
      :open="editorOpen"
      :feedback="feedback"
      @close="editorOpen = false"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.fbd-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.fbd-main {
  width: 100%;
  max-width: 900px;
  margin: 96px auto 0;
  padding: 0 16px 56px;
  flex: 1;
  box-sizing: border-box;
}

.fbd-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
  padding: 7px 14px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.fbd-back:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.fbd-state {
  min-height: 40vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--links-color);
  font-size: 14px;
}

.spinner {
  width: 26px;
  height: 26px;
  border: 3px solid var(--float-bg);
  border-top-color: var(--notice-color);
  border-radius: 50%;
  animation: fbd-spin 0.8s linear infinite;
}

@keyframes fbd-spin {
  to {
    transform: rotate(360deg);
  }
}

.fbd-card {
  padding: 24px 26px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: var(--card-color);
}

.fbd-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 18px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.fbd-head-main {
  flex: 1;
  min-width: 240px;
}

.fbd-title {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  line-height: 1.45;
  color: var(--text-color);
  word-break: break-word;
}

.fbd-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  font-size: 12.5px;
  color: var(--links-color);
}

.fbd-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.fbd-status {
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.fbd-status.is-pending {
  background: rgba(235, 170, 40, 0.16);
  color: #d99a1f;
}

.fbd-status.is-resolved {
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
}

.fbd-status.is-closed {
  background: rgba(148, 163, 184, 0.2);
  color: var(--links-color);
}

.fbd-badge {
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--float-bg);
  font-weight: 600;
}

.fbd-author {
  color: var(--links-color);
  text-decoration: none;
  transition: color 0.15s ease;
}

.fbd-author:hover {
  color: var(--text-color);
}

.fbd-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.fbd-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 14px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}

.fbd-action:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.fbd-action.danger {
  border-color: rgba(229, 72, 77, 0.45);
  color: #e5484d;
}

.fbd-action.danger:hover {
  background: rgba(229, 72, 77, 0.1);
}

.fbd-status-select {
  flex: 0 0 auto;
}

.fbd-status-select :deep(.sd-btn) {
  font-size: 13px;
}

.fbd-content {
  padding-top: 20px;
}

.fbd-comments {
  margin-top: 22px;
  padding: 22px 26px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: var(--card-color);
}

.fbd-comments-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 16px;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-color);
}

.fbd-count {
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--float-bg);
  font-size: 12px;
  font-weight: 700;
  color: var(--links-color);
}

.fbd-empty {
  margin: 8px 0 18px;
  font-size: 13.5px;
  color: var(--links-color);
}

.fbd-comment-list {
  list-style: none;
  margin: 0 0 18px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fbd-comment {
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: var(--float-bg);
}

.fbd-comment-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.fbd-comment-author {
  font-weight: 700;
  color: var(--text-color);
}

.fbd-comment-time {
  font-size: 12px;
  color: var(--links-color);
}

.fbd-comment-body :deep(.wiki-md) {
  font-size: 14px;
  line-height: 1.7;
}

.fbd-composer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fbd-comment-input {
  width: 100%;
  min-height: 96px;
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 14px;
  line-height: 1.7;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s ease;
}

.fbd-comment-input:focus {
  border-color: var(--text-color);
}

.fbd-composer-actions {
  display: flex;
  justify-content: flex-end;
}

.fbd-submit {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  border: none;
  border-radius: 12px;
  background: var(--text-color);
  color: var(--bg-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.fbd-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.fbd-login-hint {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13.5px;
  color: var(--links-color);
}

.fbd-login-btn {
  padding: 7px 16px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.fbd-login-btn:hover {
  background: var(--float-bg);
}

@media (max-width: 768px) {
  .fbd-main {
    margin-top: 84px;
    padding: 0 14px 40px;
  }

  .fbd-card,
  .fbd-comments {
    padding: 18px 16px;
  }

  .fbd-title {
    font-size: 19px;
  }

  .fbd-actions {
    width: 100%;
  }

  .fbd-status-select {
    flex: 1;
  }

  .fbd-status-select :deep(.sd-btn) {
    width: 100%;
  }
}
</style>

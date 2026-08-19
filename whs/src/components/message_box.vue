<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Trash2, X, Check, Pencil } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const { t, locale } = useI18n()
const props = defineProps({
  skipOpenAnimation: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'open-detail', 'read-changed'])
const { state: authState } = useAuth()
const { showTip } = useTips()

// 系统消息列表
const messages = ref([])
const loading = ref(true)

const isAdmin = computed(() => (authState.user?.permission ?? 0) >= 3)
const isLoggedIn = computed(() => !!authState.token)

// 发布消息对话框
const showPublish = ref(false)
// 正在编辑的消息对象（非 null 表示处于编辑模式，复用发布对话框）
const editingMessage = ref(null)
const publishTitle = ref('')
const publishContent = ref('')
const publishing = ref(false)
// 进行中的消息操作（删除/标为已读）：记录消息 id，用于禁用对应按钮并显示圆环
const busyMessageId = ref(null)

// 消息盒可见性：打开/关闭动画由 <Transition name="dialog-fade"> 统一处理
const visible = ref(true)

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

// ISO 时间 -> "YYYY-MM-DD HH:mm"
function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function fetchMessages() {
  loading.value = true
  try {
    // 系统消息（公开）+ 本人定向消息（登录时）合并
    const [sysRes, dirRes] = await Promise.all([
      fetch('/api/message/system', { headers: authHeaders() }),
      authState.token
        ? fetch(`/api/message/${authState.user?.uid}`, { headers: authHeaders() })
        : Promise.resolve(null),
    ])
    let list = []
    if (sysRes.ok) {
      const d = await sysRes.json().catch(() => ({}))
      list = d.messages || []
    }
    if (dirRes && dirRes.ok) {
      const d = await dirRes.json().catch(() => ({}))
      if (d.messages) list = list.concat(d.messages)
    }
    // 未读优先，组内按 id 倒序
    list.sort((a, b) => Number(b.id) - Number(a.id))
    list.sort((a, b) => Number(a.is_read ?? 0) - Number(b.is_read ?? 0))
    messages.value = list
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

// 标为已读（幂等）
async function markRead(m) {
  if (!isLoggedIn.value || m.is_read || busyMessageId.value !== null) return
  busyMessageId.value = m.id
  try {
    const res = await fetch(`/api/message/${m.id}/read`, {
      method: 'POST',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      m.is_read = true
      messages.value.sort((a, b) => Number(a.is_read ?? 0) - Number(b.is_read ?? 0))
      emit('read-changed')
      showTip('info', t('message.markedRead'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    busyMessageId.value = null
  }
}

async function publish() {
  if (!publishTitle.value.trim()) {
    showTip('warning', t('message.titleEmpty'))
    return
  }
  if (!publishContent.value.trim()) {
    showTip('warning', t('message.contentEmpty'))
    return
  }
  publishing.value = true
  try {
    // 编辑模式：PUT 更新自己发布的系统消息
    if (editingMessage.value) {
      const target = editingMessage.value
      const res = await fetch(`/api/admin/messages/${target.id}`, {
        method: 'PUT',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          title: publishTitle.value.trim(),
          content: publishContent.value,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        showTip('info', t('message.updated'))
        const updated = data.message
        if (updated) {
          const idx = messages.value.findIndex((x) => x.id === updated.id)
          if (idx >= 0) {
            // 编辑后所有人需重读：就地更新内容并重置为未读
            messages.value[idx] = { ...messages.value[idx], ...updated, is_read: false }
            messages.value.sort((a, b) => Number(a.is_read ?? 0) - Number(b.is_read ?? 0))
          }
        }
        emit('read-changed') // 刷新导航栏未读红点
        closeDialog()
      } else {
        showTip('error', localMessage(data))
      }
      return
    }

    // 发布模式：POST 新建系统消息
    const res = await fetch('/api/admin/messages', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ title: publishTitle.value.trim(), content: publishContent.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('message.published'))
      publishTitle.value = ''
      publishContent.value = ''
      showPublish.value = false
      fetchMessages()
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    publishing.value = false
  }
}

// 打开编辑对话框：预填当前标题与内容
function startEdit(m) {
  editingMessage.value = m
  publishTitle.value = m.title || ''
  publishContent.value = m.content || ''
}

// 关闭发布/编辑对话框并清空表单
function closeDialog() {
  showPublish.value = false
  editingMessage.value = null
  publishTitle.value = ''
  publishContent.value = ''
}

// 点击标题行：未读则先发送已读请求，再关闭消息盒并打开详情窗口
function openDetail(m) {
  if (isLoggedIn.value && !m.is_read) {
    fetch(`/api/message/${m.id}/read`, { method: 'POST', headers: authHeaders() })
      .then((res) => res.json().catch(() => ({})))
      .then((data) => {
        if (data && data.success) {
          m.is_read = true
          emit('read-changed')
        }
      })
      .catch(() => {})
  }
  emit('open-detail', m)
}

// 仅管理员可编辑/删除自己发布的消息
function canDelete(m) {
  return isAdmin.value && m.author_uid === authState.user?.uid
}

function canEdit(m) {
  return canDelete(m)
}

async function removeMessage(m) {
  if (busyMessageId.value !== null) return
  busyMessageId.value = m.id
  try {
    const res = await fetch(`/api/admin/messages/${m.id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('message.deleted'))
      messages.value = messages.value.filter((x) => x.id !== m.id)
      emit('read-changed') // 若删除的是未读消息，刷新导航栏红点
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    busyMessageId.value = null
  }
}

onMounted(() => {
  fetchMessages()
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})

// ESC：优先关闭发布/编辑对话框，其次关闭消息盒
function handleKeydown(event) {
  if (event.key !== 'Escape') return
  if (showPublish.value || editingMessage.value) {
    closeDialog()
  } else {
    close()
  }
}

// 关闭：置 visible=false，由 <Transition name="dialog-fade"> 播放离开动画，
// 动画结束后（after-leave）再通知父组件卸载
function close() {
  if (!visible.value) return
  visible.value = false
}

// 暴露 close 方法，供父组件（消息图标）在图标变叉后触发关闭
defineExpose({ close })
</script>

<template>
  <Teleport to="body">
    <!-- 打开/关闭动画：复用 style.css 统一的 dialog-fade 动画；
         skipOpenAnimation（从详情返回）时关闭 appear 首帧动画 -->
    <Transition
      name="dialog-fade"
      :appear="!props.skipOpenAnimation"
      @after-leave="emit('close')"
    >
      <div v-if="visible" class="message-overlay" @click.self="close">
        <div class="message-box">
        <header class="message-head">
          <h2>{{ t('message.title') }}</h2>
          <div class="head-actions">
            <!-- 管理员：发布消息 -->
            <button v-if="isAdmin" type="button" class="publish-btn" @click="showPublish = true">
              <Plus :size="16" />
              <span>{{ t('message.publish') }}</span>
            </button>
            <button type="button" class="head-close" :aria-label="t('message.close')" @click="close">
              <X :size="18" />
            </button>
          </div>
        </header>

        <div class="message-body">
          <p v-if="loading" class="message-empty"><span class="spinner"></span>{{ t('admin.loading') }}</p>
          <p v-else-if="messages.length === 0" class="message-empty">{{ t('message.empty') }}</p>
          <ul v-else class="message-list">
            <li v-for="m in messages" :key="m.id" class="message-item">
              <!-- 标题行：点击打开详情窗口 -->
              <div class="message-head-row" @click="openDetail(m)">
                <span class="message-title">{{ m.title || t('message.untitled') }}</span>
                <div class="message-meta">
                  <!-- 发布者 -->
                  <span v-if="m.author_name" class="message-author">{{ m.author_name }}</span>
                  <!-- 时间：最后一次修改时间（未编辑过即发布时间） -->
                  <span class="message-time">{{ formatTime(m.updated_at || m.created_at) }}</span>
                  <!-- 已编辑标记 -->
                  <span v-if="m.updated_at" class="edited-tag">{{ t('message.edited') }}</span>
                  <!-- 标为已读：未读可点；已读置灰 -->
                  <button
                    v-if="isLoggedIn"
                    type="button"
                    class="read-btn"
                    :class="{ read: m.is_read }"
                    :disabled="busyMessageId !== null"
                    :title="m.is_read ? t('message.read') : t('message.markRead')"
                    :aria-label="m.is_read ? t('message.read') : t('message.markRead')"
                    @click.stop="markRead(m)"
                  >
                    <span v-if="busyMessageId === m.id" class="spinner"></span>
                    <Check v-else :size="15" />
                  </button>
                  <button
                    v-if="canEdit(m)"
                    type="button"
                    class="edit-btn"
                    :disabled="busyMessageId !== null"
                    :title="t('message.edit')"
                    :aria-label="t('message.edit')"
                    @click.stop="startEdit(m)"
                  >
                    <Pencil :size="15" />
                  </button>
                  <button
                    v-if="canDelete(m)"
                    type="button"
                    class="delete-btn"
                    :disabled="busyMessageId !== null"
                    :title="t('message.delete')"
                    :aria-label="t('message.delete')"
                    @click.stop="removeMessage(m)"
                  >
                    <span v-if="busyMessageId === m.id" class="spinner"></span>
                    <Trash2 v-else :size="15" />
                  </button>
                </div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 发布/编辑消息对话框 -->
    <Transition name="dialog-fade">
      <div
        v-if="showPublish || editingMessage"
        class="publish-overlay"
        @click.self="closeDialog"
      >
        <div class="publish-dialog">
          <h3 class="publish-title">
            {{ editingMessage ? t('message.editTitle') : t('message.publish') }}
          </h3>
          <input
            v-model="publishTitle"
            type="text"
            class="publish-title-input"
            :placeholder="t('message.titlePlaceholder')"
          />
          <textarea
            v-model="publishContent"
            class="publish-input"
            :placeholder="t('message.publishPlaceholder')"
          ></textarea>
          <div class="publish-actions">
            <button type="button" class="btn cancel" :disabled="publishing" @click="closeDialog">
              {{ t('admin.cancel') }}
            </button>
            <button type="button" class="btn primary" :disabled="publishing" @click="publish">
              <span v-if="publishing" class="spinner"></span>
              {{ editingMessage ? t('message.save') : t('message.publish') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.message-overlay {
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

.message-box {
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

.message-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--links-color);
}

.message-head h2 {
  margin: 0;
  font-size: 20px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.publish-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.publish-btn:hover {
  background: #d99a1f;
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

.message-body {
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow-y: auto;
}

.message-empty {
  margin: 24px 0;
  text-align: center;
  color: var(--links-color);
}

.message-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.message-item {
  padding: 14px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.message-item:last-child {
  border-bottom: none;
}

.message-head-row {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  padding: 2px 0;
  border-radius: 8px;
  transition: background-color 0.15s ease;
}

.message-head-row:hover {
  background: var(--btn-hover);
}

.message-title {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.message-time {
  font-size: 12px;
  color: var(--links-color);
}

/* 发布者名称 */
.message-author {
  font-size: 12px;
  font-weight: 600;
  color: var(--links-color);
  opacity: 0.85;
}

/* 已编辑标记 */
.edited-tag {
  font-size: 11px;
  color: var(--links-color);
  border: 1px solid rgba(148, 163, 184, 0.25);
  padding: 1px 6px;
  border-radius: 999px;
  opacity: 0.85;
}

.edit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.edit-btn:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.delete-btn:hover {
  background: var(--btn-hover);
  color: #e5484d;
}

/* 标为已读按钮：未读可点，已读置灰 */
.read-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.read-btn:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.read-btn.read {
  color: #2e9e5b;
  cursor: default;
}

.read-btn.read:hover {
  background: transparent;
}

/* 发布消息对话框（独立顶层遮罩，与其它对话框一致） */
.publish-overlay {
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

.publish-dialog {
  width: min(520px, 100%);
  padding: 24px;
  border-radius: 16px;
  /* 与消息盒一致的毛玻璃半透明背景 */
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  color: var(--text-color);
}

.publish-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 700;
}

.publish-title-input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  margin-bottom: 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-weight: 600;
  outline: none;
  transition: border-color 0.2s ease;
}

.publish-title-input:focus {
  border-color: var(--text-color);
}

.publish-input {
  width: 100%;
  box-sizing: border-box;
  min-height: 160px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s ease;
}

.publish-input:focus {
  border-color: var(--text-color);
}

/* 按钮靠左：取消在前，发布在后 */
.publish-actions {
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
  transition: opacity 0.2s ease;
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

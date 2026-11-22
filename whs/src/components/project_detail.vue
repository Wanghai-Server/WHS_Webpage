<script setup>
/**
 * 工程详情弹窗：展示元数据，并提供认领 / 完成 / 删除 / 编辑描述与备注。
 *
 * - 权限全部以后端返回的 viewer 标记为准；
 * - 描述按全站统一 Markdown 渲染，备注为纯文本；
 * - 多账号时认领可选择账号（默认主账号 / 本地记忆）。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Link2, X } from 'lucide-vue-next'
import MarkdownView from './markdown_view.vue'
import MarkdownEditer from './markdown_editer.vue'
import ProjectAccountDialog from './project_account_dialog.vue'
import { useAuth } from '../composables/useAuth'
import { useDialogBox } from '../composables/useDialogBox'
import { useTips } from '../composables/useTips'

const props = defineProps({
  open: { type: Boolean, default: false },
  project: { type: Object, default: null },
  viewer: { type: Object, default: () => ({}) },
  accounts: { type: Array, default: () => [] },
  online: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'changed', 'deleted'])

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()
const dialogBox = useDialogBox()

const editing = ref(false)
const description = ref('')
const remark = ref('')
const claimDialogOpen = ref(false)
const busy = ref(false)

const isLoggedIn = computed(() => !!authState.token)
const canClaim = computed(() => props.online && props.viewer?.can_claim)
const canComplete = computed(() => props.online && props.viewer?.can_complete)
const canDelete = computed(() => props.online && props.viewer?.can_delete)
const canEdit = computed(() => props.online && props.viewer?.can_edit)

const statusKey = computed(() => {
  const status = props.project?.status || 'unclaimed'
  return `projects.status${status.charAt(0).toUpperCase()}${status.slice(1)}`
})

const statusClass = computed(() => props.project?.status || 'unclaimed')

function localMessage(data) {
  const message = data && data.message
  if (!message) return t('auth.request_failed')
  return message[locale.value] || message.zh || message.en || ''
}

function authHeaders(extra = {}) {
  return {
    ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
    ...extra,
  }
}

async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: authHeaders(body ? { 'Content-Type': 'application/json' } : {}),
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data }
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function reset() {
  editing.value = false
  busy.value = false
  claimDialogOpen.value = false
  description.value = props.project?.description || ''
  remark.value = props.project?.remark || ''
}

watch(
  () => [props.open, props.project?.name, props.project?.updated_at],
  () => {
    if (props.open) reset()
  }
)

function applyResult(data) {
  emit('changed', data)
  editing.value = false
}

function openClaim() {
  if (!canClaim.value) return
  claimDialogOpen.value = true
}

async function confirmClaim(player) {
  if (!props.online || !props.project || !player) return
  claimDialogOpen.value = false
  busy.value = true
  try {
    const { ok, data } = await request('POST', '/api/projects/claim', {
      name: props.project.name,
      player,
    })
    if (ok) {
      showTip('info', t('projects.claimSuccess'))
      applyResult(data)
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

async function startEdit() {
  if (!canEdit.value || !props.project) return
  const confirmed = await dialogBox.confirm({
    title: t('projects.editConfirmTitle'),
    message: t('projects.editConfirmMessage', { name: props.project.name }),
  })
  if (!confirmed) return
  // 每次进入编辑都用当前工程内容重置草稿，取消后再次编辑不会带入未保存内容
  description.value = props.project.description || ''
  remark.value = props.project.remark || ''
  editing.value = true
}

async function complete() {
  if (!props.online || !props.project) return
  const confirmed = await dialogBox.confirm({
    title: t('projects.completeConfirmTitle'),
    message: t('projects.completeConfirmMessage', { name: props.project.name }),
  })
  if (!confirmed) return
  busy.value = true
  try {
    const { ok, data } = await request('POST', '/api/projects/complete', {
      name: props.project.name,
    })
    if (ok) {
      showTip('info', t('projects.completeSuccess'))
      applyResult(data)
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

async function remove() {
  if (!props.online || !props.project) return
  const confirmed = await dialogBox.confirm({
    title: t('projects.deleteConfirmTitle'),
    message: t('projects.deleteConfirmMessage', { name: props.project.name }),
    danger: true,
  })
  if (!confirmed) return
  busy.value = true
  try {
    const { ok, data } = await request(
      'DELETE',
      `/api/projects?name=${encodeURIComponent(props.project.name)}`
    )
    if (ok) {
      showTip('info', t('projects.deleteSuccess'))
      emit('deleted')
      emit('close')
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

async function saveMeta() {
  if (!props.online || !props.project) return
  busy.value = true
  try {
    const { ok, data } = await request('PUT', '/api/projects/meta', {
      name: props.project.name,
      description: description.value,
      remark: remark.value,
    })
    if (ok) {
      showTip('info', t('projects.saveSuccess'))
      applyResult(data)
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
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="open && project" class="dialog-overlay">
        <div class="dialog pd-dialog">
          <header class="pd-head">
            <div class="pd-head-main">
              <h2 class="pd-title">{{ project.name }}</h2>
              <span class="pd-status" :class="statusClass">{{ t(statusKey) }}</span>
            </div>
            <button type="button" class="pd-close" :aria-label="t('projects.close')" @click="emit('close')">
              <X :size="18" />
            </button>
          </header>

          <div class="pd-body">
            <p v-if="!online" class="pd-offline">
              {{ t('projects.serverOffline') }} — {{ t('projects.serverOfflineHint') }}
            </p>

            <dl class="pd-meta">
              <div class="pd-meta-row">
                <dt>{{ t('projects.creator') }}</dt>
                <dd>
                  <RouterLink v-if="project.creator_uid" :to="`/user/${project.creator_uid}`">
                    {{ project.creator }}
                  </RouterLink>
                  <span v-else>{{ project.creator || t('projects.none') }}</span>
                </dd>
              </div>
              <div class="pd-meta-row">
                <dt>{{ t('projects.claimants') }}</dt>
                <dd class="pd-claimants">
                  <template v-if="project.claimants.length">
                    <span v-for="(claimant, index) in project.claimants" :key="claimant.name">
                      <template v-if="index > 0">, </template>
                      <RouterLink v-if="claimant.uid" :to="`/user/${claimant.uid}`">
                        {{ claimant.name }}
                      </RouterLink>
                      <span v-else>{{ claimant.name }}</span>
                    </span>
                  </template>
                  <span v-else>{{ t('projects.none') }}</span>
                </dd>
              </div>
              <div v-if="project.created_at" class="pd-meta-row">
                <dt>{{ t('projects.createdAt') }}</dt>
                <dd>{{ formatTime(project.created_at) }}</dd>
              </div>
              <div v-if="project.claimed_at" class="pd-meta-row">
                <dt>{{ t('projects.claimedAt') }}</dt>
                <dd>{{ formatTime(project.claimed_at) }}</dd>
              </div>
              <div v-if="project.completed_at" class="pd-meta-row">
                <dt>{{ t('projects.completedAt') }}</dt>
                <dd>{{ formatTime(project.completed_at) }}</dd>
              </div>
              <div v-if="project.updated_at" class="pd-meta-row">
                <dt>{{ t('projects.updatedAt') }}</dt>
                <dd>{{ formatTime(project.updated_at) }}</dd>
              </div>
            </dl>

            <Transition name="pd-edit" mode="out-in">
              <div :key="editing ? 'edit' : 'view'" class="pd-sections">
                <section class="pd-section">
                  <h3 class="pd-section-title">
                    {{ t('projects.description') }}
                    <Link2 v-if="editing" :size="14" />
                  </h3>
                  <MarkdownEditer
                    v-if="editing"
                    v-model="description"
                    :placeholder="t('projects.descriptionHint')"
                    :min-height="180"
                    :show-lang-switch="false"
                  />
                  <MarkdownView v-else-if="project.description" :content="project.description" />
                  <p v-else class="pd-empty">{{ t('projects.descriptionEmpty') }}</p>
                </section>

                <section class="pd-section">
                  <h3 class="pd-section-title">{{ t('projects.remark') }}</h3>
                  <textarea
                    v-if="editing"
                    v-model="remark"
                    class="pd-remark-input"
                    maxlength="500"
                    rows="4"
                    :placeholder="t('projects.remarkHint')"
                  ></textarea>
                  <p v-else-if="project.remark" class="pd-remark">{{ project.remark }}</p>
                  <p v-else class="pd-empty">{{ t('projects.remarkEmpty') }}</p>
                </section>
              </div>
            </Transition>
          </div>

          <footer class="pd-foot">
            <template v-if="editing">
              <button type="button" class="pd-btn ghost" :disabled="busy" @click="editing = false">
                {{ t('projects.cancel') }}
              </button>
              <button type="button" class="pd-btn primary" :disabled="busy" @click="saveMeta">
                <span v-if="busy" class="spinner"></span>
                {{ t('projects.save') }}
              </button>
            </template>
            <template v-else>
              <span v-if="!isLoggedIn" class="pd-login-hint">{{ t('projects.loginRequired') }}</span>
              <button
                v-if="canDelete"
                type="button"
                class="pd-btn danger"
                :disabled="busy"
                @click="remove"
              >
                {{ t('projects.delete') }}
              </button>
              <button
                v-if="canEdit"
                type="button"
                class="pd-btn ghost"
                :disabled="busy"
                @click="startEdit"
              >
                {{ t('projects.edit') }}
              </button>
              <button
                v-if="canComplete"
                type="button"
                class="pd-btn ghost"
                :disabled="busy"
                @click="complete"
              >
                {{ t('projects.complete') }}
              </button>
              <button
                v-if="canClaim"
                type="button"
                class="pd-btn primary"
                :disabled="busy || !online"
                @click="openClaim"
              >
                {{ t('projects.claim') }}
              </button>
            </template>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>

  <ProjectAccountDialog
    :open="claimDialogOpen"
    :title="t('projects.claimDialogTitle')"
    :message="t('projects.claimDialogMessage', { name: project?.name || '' })"
    :accounts="accounts"
    :busy="busy"
    :confirm-text="t('projects.claim')"
    @close="claimDialogOpen = false"
    @confirm="confirmClaim"
  />
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
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}

.dialog {
  width: min(760px, 100%);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 16px;
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  color: var(--text-color);
  overflow: hidden;
}

.pd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.pd-head-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.pd-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pd-status {
  flex-shrink: 0;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #1f2937;
}

.pd-status.unclaimed {
  background: #ebaa28;
}

.pd-status.claimed {
  background: #e5484d;
  color: #fff;
}

.pd-status.completed {
  background: #3fb950;
  color: #fff;
}

.pd-close {
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

.pd-close:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.pd-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.pd-offline {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(235, 170, 40, 0.14);
  color: #b7791f;
  font-size: 13px;
  line-height: 1.5;
}

.pd-meta {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pd-meta-row {
  display: flex;
  gap: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.pd-meta-row dt {
  flex-shrink: 0;
  width: 72px;
  color: var(--links-color);
  font-weight: 600;
}

.pd-meta-row dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.pd-meta-row a {
  color: var(--links-color);
  text-decoration: none;
}

.pd-meta-row a:hover {
  color: var(--text-color);
  text-decoration: underline;
}

.pd-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 查看 / 编辑切换：整块内容淡入淡出 + 轻微上移，避免生硬跳变 */
.pd-sections {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.pd-edit-enter-active,
.pd-edit-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.pd-edit-enter-from,
.pd-edit-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.pd-section-title {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 700;
  color: var(--links-color);
}

.pd-section-title svg {
  opacity: 0.7;
}

.pd-empty {
  margin: 0;
  font-size: 13px;
  color: var(--links-color);
}

.pd-remark {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.pd-remark-input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  background: var(--bg-color);
  color: var(--text-color);
  font: inherit;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
}

.pd-remark-input:focus {
  outline: 2px solid rgba(235, 170, 40, 0.4);
  outline-offset: 1px;
}

.pd-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  padding: 14px 22px 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.pd-login-hint {
  margin-right: auto;
  font-size: 13px;
  color: var(--links-color);
}

.pd-btn {
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

.pd-btn.ghost {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.pd-btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.pd-btn.danger {
  border: none;
  background: #e5484d;
  color: #fff;
}

.pd-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .pd-head {
    padding: 16px;
  }

  .pd-body {
    padding: 14px 16px;
  }

  .pd-foot {
    padding: 12px 16px 16px;
  }
}
</style>

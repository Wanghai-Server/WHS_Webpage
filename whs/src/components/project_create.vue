<script setup>
/**
 * 发起工程弹窗（permission >= 3）。
 *
 * - 输入工程名称，选择使用的 MC 账号（多账号时显示选择器）；
 * - POST /api/projects；成功后通知父组件刷新列表。
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from 'lucide-vue-next'
import ProjectAccountDialog from './project_account_dialog.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { preferredPlayer } from '../composables/useProjectPlayer'

const props = defineProps({
  open: { type: Boolean, default: false },
  accounts: { type: Array, default: () => [] },
  defaultAccount: { type: String, default: '' },
})
const emit = defineEmits(['close', 'created'])

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

const name = ref('')
const player = ref('')
const submitting = ref(false)
const confirmOpen = ref(false)

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

// 每次打开时重置表单，并恢复本地记住的账号（失效则回退主账号）
function resetForm() {
  name.value = ''
  submitting.value = false
  confirmOpen.value = false
  player.value = preferredPlayer(props.accounts, props.defaultAccount)
}

watch(
  () => props.open,
  (open) => {
    if (open) resetForm()
  }
)

// 账号列表可能晚于弹窗加载完成：补一次默认选择
watch(
  () => props.accounts,
  (accounts) => {
    if (props.open && !player.value && accounts.length) {
      player.value = preferredPlayer(accounts, props.defaultAccount)
    }
  }
)

function submit() {
  if (submitting.value) return
  const projectName = name.value.trim()
  if (!projectName) {
    showTip('warning', t('projects.nameRequired'))
    return
  }
  if (projectName.length > 32) {
    showTip('warning', t('projects.nameTooLong'))
    return
  }
  if (!props.accounts.length) {
    showTip('warning', t('projects.bindAccount'))
    return
  }
  // 多账号：先弹出确认浮层选择账号；单账号直接创建
  if (props.accounts.length > 1) {
    confirmOpen.value = true
    return
  }
  createProject(props.accounts[0].name)
}

async function createProject(selectedPlayer) {
  if (submitting.value) return
  submitting.value = true
  try {
    const res = await fetch('/api/projects', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ name: name.value.trim(), player: selectedPlayer }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('projects.createSuccess'))
      emit('created', data)
      emit('close')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    submitting.value = false
  }
}

function onConfirmCreate(selectedPlayer) {
  confirmOpen.value = false
  createProject(selectedPlayer)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="open" class="dialog-overlay">
        <div class="dialog rc-dialog">
          <header class="rc-head">
            <h2 class="rc-title">{{ t('projects.createTitle') }}</h2>
            <button type="button" class="rc-close" :aria-label="t('projects.close')" @click="emit('close')">
              <X :size="18" />
            </button>
          </header>

          <div class="rc-body">
            <label class="float-field">
              <input v-model="name" type="text" placeholder=" " maxlength="32" />
              <span class="float-label">{{ t('projects.nameLabel') }}</span>
            </label>
            <p class="rc-hint">{{ t('projects.nameHint') }}</p>
          </div>

          <footer class="rc-foot">
            <button type="button" class="rc-btn ghost" @click="emit('close')">
              {{ t('projects.cancel') }}
            </button>
            <button type="button" class="rc-btn primary" :disabled="submitting" @click="submit">
              <span v-if="submitting" class="spinner"></span>
              {{ t('projects.create') }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>

  <ProjectAccountDialog
    :open="confirmOpen"
    :title="t('projects.createConfirmTitle')"
    :message="t('projects.createConfirmMessage', { name: name.trim() })"
    :accounts="accounts"
    :default-player="player"
    :busy="submitting"
    :confirm-text="t('projects.create')"
    @close="confirmOpen = false"
    @confirm="onConfirmCreate"
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
  width: min(560px, 100%);
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

.rc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.rc-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.rc-close {
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

.rc-close:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.rc-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rc-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--links-color);
}

.rc-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 22px 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.rc-btn {
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

.rc-btn.ghost {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.rc-btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.rc-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .rc-head {
    padding: 16px;
  }

  .rc-body {
    padding: 14px 16px;
  }

  .rc-foot {
    padding: 12px 16px 16px;
  }
}
</style>

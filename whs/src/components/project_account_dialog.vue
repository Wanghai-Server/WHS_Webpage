<script setup>
/**
 * 工程操作确认弹窗（账号选择版）。
 *
 * - 用于"认领工程"与"发起工程"的二次确认：展示操作说明，并在多账号时选择账号；
 * - 账号选择器与确认按钮在同一浮层内，不再把选择器内嵌进工程详情/发起表单；
 * - 弹窗层级高于详情 / 发起弹窗（z-index 9700）。
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from 'lucide-vue-next'
import McAccountPicker from './mc_account_picker.vue'
import { preferredPlayer } from '../composables/useProjectPlayer'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  message: { type: String, default: '' },
  accounts: { type: Array, default: () => [] },
  defaultPlayer: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  confirmText: { type: String, default: '' },
})
const emit = defineEmits(['close', 'confirm'])

const { t } = useI18n()
const player = ref('')

watch(
  () => props.open,
  (open) => {
    if (open) player.value = preferredPlayer(props.accounts, props.defaultPlayer)
  }
)

function confirm() {
  if (props.busy || !player.value) return
  emit('confirm', player.value)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="open" class="dialog-overlay account-confirm-overlay">
        <div class="dialog ac-dialog">
          <header class="ac-head">
            <h2 class="ac-title">{{ title }}</h2>
            <button type="button" class="ac-close" :aria-label="t('projects.close')" @click="emit('close')">
              <X :size="18" />
            </button>
          </header>

          <div class="ac-body">
            <p class="ac-message">{{ message }}</p>
            <McAccountPicker
              v-if="accounts.length > 1"
              v-model="player"
              :accounts="accounts"
            />
          </div>

          <footer class="ac-foot">
            <button type="button" class="ac-btn ghost" :disabled="busy" @click="emit('close')">
              {{ t('projects.cancel') }}
            </button>
            <button type="button" class="ac-btn primary" :disabled="busy || !player" @click="confirm">
              <span v-if="busy" class="spinner"></span>
              {{ confirmText || t('projects.confirm') }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.account-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 9700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.55);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}

.ac-dialog {
  width: min(520px, 100%);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 16px;
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.24);
  color: var(--text-color);
  overflow: hidden;
}

.ac-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.ac-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.ac-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.ac-close:hover {
  color: var(--text-color);
  background: var(--float-bg);
}

.ac-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ac-message {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.ac-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.ac-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 20px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s ease, background-color 0.15s ease;
}

.ac-btn.ghost {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.ac-btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.ac-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

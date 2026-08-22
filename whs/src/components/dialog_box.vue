<script setup>
/**
 * 全局对话框组件（替代 window.confirm / window.alert）。
 *
 * - 状态由 useDialogBox 单例持有，本组件在 App.vue 全局挂载一次；
 * - confirm 型：取消 / 确定；alert 型：仅确定；
 * - 支持 danger 危险样式、点击遮罩或按 ESC 取消（均以 false 关闭）。
 */
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, Info } from 'lucide-vue-next'
import { useDialogBox } from '../composables/useDialogBox'

const { t } = useI18n()
const dialog = useDialogBox()

function cancel() {
  dialog.close(false)
}

function confirm() {
  dialog.close(true)
}

function onKeydown(e) {
  if (dialog.state.visible && e.key === 'Escape') cancel()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="dialog.state.visible" class="dialog-overlay" @click.self="cancel">
        <div class="dialog-box" role="alertdialog" aria-modal="true">
          <AlertTriangle v-if="dialog.state.danger" :size="26" class="dialog-icon is-danger" />
          <Info v-else :size="26" class="dialog-icon" />

          <h3 v-if="dialog.state.title" class="dialog-title">{{ dialog.state.title }}</h3>
          <p class="dialog-message">{{ dialog.state.message }}</p>

          <div class="dialog-actions">
            <button
              v-if="dialog.state.type === 'confirm'"
              type="button"
              class="dialog-btn"
              @click="cancel"
            >
              {{ dialog.state.cancelText || t('dialog.cancel') }}
            </button>
            <button
              type="button"
              class="dialog-btn primary"
              :class="{ danger: dialog.state.danger }"
              @click="confirm"
            >
              {{ dialog.state.confirmText || t('dialog.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
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

.dialog-box {
  width: min(420px, 90vw);
  box-sizing: border-box;
  padding: 28px 26px;
  border-radius: 16px;
  /* 透明背景 + 毛玻璃（与全站导航栏 / 消息弹窗同款） */
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  text-align: center;
}

.dialog-icon {
  color: var(--notice-color);
  margin-bottom: 10px;
}

.dialog-icon.is-danger {
  color: #e5484d;
}

.dialog-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.dialog-message {
  margin: 0 0 20px;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--links-color);
  word-break: break-word;
}

.dialog-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.dialog-btn {
  padding: 9px 20px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--text-color);
  font-size: 13.5px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.dialog-btn:hover {
  background: var(--float-bg);
}

.dialog-btn.primary {
  background: var(--notice-color);
  border-color: transparent;
  font-weight: 600;
}

.dialog-btn.primary.danger {
  background: #e5484d;
  color: #ffffff;
}

/* 入场 / 退场动画（与全站 dialog-fade 一致） */
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-active .dialog-box,
.dialog-fade-leave-active .dialog-box {
  transition:
    transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.25s ease;
}

.dialog-fade-enter-from .dialog-box,
.dialog-fade-leave-to .dialog-box {
  opacity: 0;
  transform: translateY(12px) scale(0.96);
}
</style>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import { Eye, EyeOff } from 'lucide-vue-next'
import { useTips } from '../composables/useTips'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'
import { sha256 } from '../composables/sha256'

const emit = defineEmits(['close'])

const { t, locale } = useI18n()
const { showTip } = useTips()
const hcaptchaSiteKey = useHcaptchaSiteKey()

const EMAIL_RE = /^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/
const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/

// 第一页：验证身份（验证码发送到用户输入的邮箱）
const email = ref('')
const code = ref('')
const hcaptchaToken = ref('')
const sendCooldown = ref(0)
let cooldownTimer = null

// 第二页：新密码
const newPassword = ref('')
const confirmPassword = ref('')
// 新密码 + 确认密码共用一个显示/隐藏按钮（按钮在“确认密码”框内）
const showPasswords = ref(false)

const step = ref('verify') // 'verify' | 'new'
const loading = ref(false)
const sendingCode = ref(false)
const visible = ref(true) // 控制进入/离开动画；关闭时先播放离开动画再通知父组件

const CLOSE_MS = 260 // 略大于 dialog-fade 离开动画时长(250ms)，保证动画播完再卸载

// hCaptcha 主题跟随站点亮/暗色
const captchaTheme = computed(() => {
  const html = document.documentElement
  if (html.classList.contains('dark')) return 'dark'
  if (html.classList.contains('light')) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
})

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

function onVerify(token) {
  hcaptchaToken.value = token
}

function onCaptchaExpired() {
  hcaptchaToken.value = ''
  showTip('warning', t('auth.captcha_expired'))
}

function onCaptchaError(err) {
  hcaptchaToken.value = ''
  console.warn('hCaptcha error:', err)
}

// 必须先完成人机验证，才能获取验证码
async function sendCode() {
  if (sendCooldown.value > 0 || sendingCode.value) return
  if (!EMAIL_RE.test(email.value.trim())) {
    showTip('warning', t('auth.email_invalid'))
    return
  }
  if (!hcaptchaToken.value) {
    showTip('warning', t('auth.captcha_required'))
    return
  }
  sendingCode.value = true
  try {
    const res = await fetch('/api/user/send_code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value.trim(), locale: locale.value, hcaptcha_response: hcaptchaToken.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok && data.success) {
      showTip('info', t('auth.code_sent'))
      sendCooldown.value = 60
      if (cooldownTimer) clearInterval(cooldownTimer)
      cooldownTimer = setInterval(() => {
        sendCooldown.value -= 1
        if (sendCooldown.value <= 0) {
          clearInterval(cooldownTimer)
          cooldownTimer = null
        }
      }, 1000)
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    sendingCode.value = false
  }
}

// 第一页 -> 后端预验证（邮箱 + 验证码），通过后进入第二页（人机验证仅发送验证码时需要）
async function goNext() {
  if (!email.value.trim()) { showTip('warning', t('auth.email_required')); return }
  if (!EMAIL_RE.test(email.value.trim())) { showTip('warning', t('auth.email_invalid')); return }
  if (!code.value.trim()) { showTip('warning', t('auth.code_required')); return }
  loading.value = true
  try {
    const res = await fetch('/api/user/password_reset_verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.value.trim(),
        code: code.value.trim(),
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      step.value = 'new'
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

// 第二页 -> 提交重置密码，成功后关闭组件
async function resetPassword() {
  if (!newPassword.value) { showTip('warning', t('auth.password_required')); return }
  if (newPassword.value !== confirmPassword.value) { showTip('warning', t('auth.password_mismatch')); return }
  if (!PASSWORD_ASCII_RE.test(newPassword.value)) { showTip('warning', t('auth.password_ascii')); return }
  loading.value = true
  try {
    const newHash = await sha256(newPassword.value)
    const res = await fetch('/api/user/password_reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.value.trim(),
        code: code.value.trim(),
        new_password: newHash,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.passwordSaved'))
      // 先播放离开动画，动画结束后再通知父组件关闭
      visible.value = false
      setTimeout(() => emit('close'), CLOSE_MS)
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

function cancel() {
  if (!visible.value) return
  visible.value = false
  setTimeout(() => emit('close'), CLOSE_MS)
}

// ESC 关闭对话框
function handleKeydown(e) {
  if (e.key === 'Escape') cancel()
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (cooldownTimer) {
    clearInterval(cooldownTimer)
    cooldownTimer = null
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade" appear>
      <div v-if="visible" class="overlay">
        <div class="dialog">
        <!-- 第一页：验证身份 -->
        <template v-if="step === 'verify'">
          <h3 class="title">{{ t('settings.passwordSection') }}</h3>
          <p class="hint">{{ t('settings.verifyHint') }}</p>

          <div class="field">
            <label class="float-field">
              <input v-model="email" type="email" placeholder=" " autocomplete="email" />
              <span class="float-label">{{ t('settings.email') }}</span>
            </label>
          </div>

          <div class="field">
            <div class="code-row">
              <label class="float-field">
                <input v-model="code" type="text" placeholder=" " autocomplete="one-time-code" />
                <span class="float-label">{{ t('auth.code') }}</span>
              </label>
              <button type="button" class="btn ghost" :disabled="sendCooldown > 0 || sendingCode" @click="sendCode">
                <span v-if="sendingCode" class="spinner"></span>
                {{ sendCooldown > 0 ? `${sendCooldown}s` : t('settings.sendCode') }}
              </button>
            </div>
          </div>

          <div class="h-captcha">
            <VueHcaptcha
              v-if="hcaptchaSiteKey"
              :sitekey="hcaptchaSiteKey"
              :theme="captchaTheme"
              api-endpoint="https://js.hcaptcha.com/1/api.js"
              @verify="onVerify"
              @expired="onCaptchaExpired"
              @error="onCaptchaError"
            />
          </div>

          <div class="actions">
            <button class="btn cancel" :disabled="loading" @click="cancel">{{ t('admin.cancel') }}</button>
            <button class="btn primary" :disabled="loading" @click="goNext">
              <span v-if="loading" class="spinner"></span>
              {{ t('settings.next') }}
            </button>
          </div>
        </template>

        <!-- 第二页：输入新密码 -->
        <template v-else>
          <h3 class="title">{{ t('settings.passwordSection') }}</h3>

          <div class="field">
            <label class="float-field">
              <input
                v-model="newPassword"
                :type="showPasswords ? 'text' : 'password'"
                placeholder=" "
                autocomplete="new-password"
              />
              <span class="float-label">{{ t('settings.newPassword') }}</span>
            </label>
          </div>

          <div class="field pwd-field">
            <label class="float-field">
              <input
                v-model="confirmPassword"
                :type="showPasswords ? 'text' : 'password'"
                placeholder=" "
                autocomplete="new-password"
              />
              <span class="float-label">{{ t('settings.confirmPassword') }}</span>
            </label>
            <button
              type="button"
              class="pwd-toggle"
              :aria-label="showPasswords ? t('auth.hide_password') : t('auth.show_password')"
              :title="showPasswords ? t('auth.hide_password') : t('auth.show_password')"
              :aria-pressed="showPasswords"
              @click="showPasswords = !showPasswords"
            >
              <EyeOff v-if="showPasswords" :size="18" />
              <Eye v-else :size="18" />
            </button>
          </div>

          <div class="actions">
            <button class="btn primary" :disabled="loading" @click="resetPassword">
              <span v-if="loading" class="spinner"></span>
              {{ t('settings.change') }}
            </button>
          </div>
        </template>
      </div>
    </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.overlay {
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

.dialog {
  /* 半透明毛玻璃对话框：浮动标签底色跟随对话框背景，避免白色补丁 */
  --float-label-bg: var(--navbar-bg);
  width: min(420px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  padding: 24px;
  border-radius: 16px;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  color: var(--text-color);
}

.title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
}

.hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--links-color);
}

.field {
  margin-bottom: 14px;
}

.code-row {
  display: flex;
  gap: 10px;
}

.h-captcha {
  margin-bottom: 16px;
}

.h-captcha :deep(iframe) {
  width: 100% !important;
}

/* 按钮靠左：取消在前，主操作在后 */
.actions {
  display: flex;
  justify-content: flex-start;
  gap: 10px;
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
  transition: opacity 0.2s ease;
}

.btn.cancel,
.btn.ghost {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn.ghost {
  flex-shrink: 0;
  color: var(--links-color);
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

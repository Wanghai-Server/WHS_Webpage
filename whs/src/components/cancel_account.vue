<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import { Eye, EyeOff } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'
import { sha256 } from '../composables/sha256'

const props = defineProps({
  uid: { type: Number, required: true },
})
const emit = defineEmits(['close'])

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState, clearAuth } = useAuth()
const { showTip } = useTips()
const hcaptchaSiteKey = useHcaptchaSiteKey()

const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/

// 验证项：邮箱验证码（发到当前登录邮箱）+ 旧密码 + 人机验证
const code = ref('')
const oldPassword = ref('')
const showPassword = ref(false)
const hcaptchaToken = ref('')
const sendCooldown = ref(0)
let cooldownTimer = null

const loading = ref(false)
const sendingCode = ref(false)
const visible = ref(true) // 控制进入/离开动画

// 两段式确认：第一次点击“注销”进入待确认态，再次点击才执行
const confirmArmed = ref(false)
let confirmTimer = null
const CONFIRM_RESET_MS = 5000

const CLOSE_MS = 260 // 略大于 dialog-fade 离开动画时长

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

function authHeaders(extra = {}) {
  return {
    ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
    ...extra,
  }
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
  if (!hcaptchaToken.value) {
    showTip('warning', t('auth.captcha_required'))
    return
  }
  const email = authState.user?.email || ''
  if (!email) {
    showTip('error', t('auth.request_failed'))
    return
  }
  sendingCode.value = true
  try {
    const res = await fetch('/api/user/send_code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, locale: locale.value, hcaptcha_response: hcaptchaToken.value }),
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

// 注销：首次点击进入待确认态，再次点击提交后端验证并删除
async function doCancel() {
  if (!confirmArmed.value) {
    confirmArmed.value = true
    if (confirmTimer) clearTimeout(confirmTimer)
    confirmTimer = setTimeout(() => {
      confirmArmed.value = false
    }, CONFIRM_RESET_MS)
    return
  }
  if (!code.value.trim()) { showTip('warning', t('auth.code_required')); return }
  if (!oldPassword.value) { showTip('warning', t('auth.password_required')); return }
  loading.value = true
  try {
    const oldHash = await sha256(oldPassword.value)
    const res = await fetch(`/api/user/${props.uid}/cancel`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        old_password: oldHash,
        code: code.value.trim(),
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.cancelSuccess'))
      // 先播放离开动画，随后清除登录态并跳转首页
      visible.value = false
      clearAuth()
      setTimeout(() => {
        emit('close')
        router.push('/')
      }, CLOSE_MS)
    } else {
      confirmArmed.value = false
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
  if (confirmTimer) {
    clearTimeout(confirmTimer)
    confirmTimer = null
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade" appear>
      <div v-if="visible" class="overlay">
        <div class="dialog">
          <h3 class="title">{{ t('settings.cancelAccount') }}</h3>
          <p class="hint">{{ t('settings.cancelHint') }}</p>

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

          <div class="field pwd-field">
            <label class="float-field">
              <input
                v-model="oldPassword"
                :type="showPassword ? 'text' : 'password'"
                placeholder=" "
                autocomplete="current-password"
              />
              <span class="float-label">{{ t('settings.currentPassword') }}</span>
            </label>
            <button
              type="button"
              class="pwd-toggle"
              :aria-label="showPassword ? t('auth.hide_password') : t('auth.show_password')"
              :title="showPassword ? t('auth.hide_password') : t('auth.show_password')"
              :aria-pressed="showPassword"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" :size="18" />
              <Eye v-else :size="18" />
            </button>
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
            <button type="button" class="btn cancel" :disabled="loading" @click="cancel">
              {{ t('admin.cancel') }}
            </button>
            <button type="button" class="btn danger" :class="{ armed: confirmArmed }" :disabled="loading" @click="doCancel">
              <span v-if="loading" class="spinner"></span>
              {{ confirmArmed ? t('settings.confirmCancel') : t('settings.cancel') }}
            </button>
          </div>
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
  color: #e5484d;
  line-height: 1.6;
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

/* 按钮靠左：取消在前，注销在后 */
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
  transition: opacity 0.2s ease, background-color 0.2s ease;
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

.btn.danger {
  border: none;
  background: #e5484d;
  color: #ffffff;
}

.btn.danger.armed {
  background: #b22f35;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

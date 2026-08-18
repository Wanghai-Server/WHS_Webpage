<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'
import { sha256 } from '../composables/sha256'

const props = defineProps({
  uid: { type: Number, required: true },
})
const emit = defineEmits(['close', 'done'])

const { t, locale } = useI18n()
const { state: authState, fetchMe } = useAuth()
const { showTip } = useTips()
const hcaptchaSiteKey = useHcaptchaSiteKey()

const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/

// 第一页：验证身份（验证码发送到当前登录邮箱，界面不展示邮箱）
const code = ref('')
const oldPassword = ref('')
const hcaptchaToken = ref('')
const sendCooldown = ref(0)
let cooldownTimer = null

// 第二页：新密码
const newPassword = ref('')
const confirmPassword = ref('')
const oldPasswordHash = ref('') // 第一页验证通过后保存，第二页提交时使用

const step = ref('verify') // 'verify' | 'new'
const loading = ref(false)
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
  // hCaptcha error 多为瞬时事件，仅清空 token 记录日志
  hcaptchaToken.value = ''
  console.warn('hCaptcha error:', err)
}

async function sendCode() {
  if (sendCooldown.value > 0) return
  // 必须先完成人机验证，才能获取验证码
  if (!hcaptchaToken.value) {
    showTip('warning', t('auth.captcha_required'))
    return
  }
  // 验证码发送到当前登录邮箱（后端 /api/user/send_code 按该邮箱发码）
  const email = authState.user?.email || ''
  if (!email) {
    showTip('error', t('auth.request_failed'))
    return
  }
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
}

// 第一页 -> 提交四项验证，通过后进入第二页
async function goNext() {
  if (!code.value.trim()) { showTip('warning', t('auth.code_required')); return }
  if (!oldPassword.value) { showTip('warning', t('auth.password_required')); return }
  if (!hcaptchaToken.value) { showTip('warning', t('auth.captcha_required')); return }
  loading.value = true
  try {
    const oldHash = await sha256(oldPassword.value)
    const headers = { 'Content-Type': 'application/json' }
    if (authState.token) headers.Authorization = `Bearer ${authState.token}`
    const res = await fetch(`/api/user/${props.uid}/password_verify`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        code: code.value.trim(),
        old_password: oldHash,
        hcaptcha_response: hcaptchaToken.value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      oldPasswordHash.value = oldHash
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

// 第二页 -> 提交新密码，成功后关闭组件
async function changePassword() {
  if (!newPassword.value) { showTip('warning', t('auth.password_required')); return }
  if (newPassword.value !== confirmPassword.value) { showTip('warning', t('auth.password_mismatch')); return }
  if (!PASSWORD_ASCII_RE.test(newPassword.value)) { showTip('warning', t('auth.password_ascii')); return }
  loading.value = true
  try {
    const newHash = await sha256(newPassword.value)
    const headers = { 'Content-Type': 'application/json' }
    if (authState.token) headers.Authorization = `Bearer ${authState.token}`
    const res = await fetch(`/api/user/${props.uid}/password`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ old_password: oldPasswordHash.value, new_password: newHash }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.passwordSaved'))
      fetchMe() // 密码变更：刷新公共用户数据
      // 先播放离开动画，动画结束后再通知父组件卸载
      visible.value = false
      setTimeout(() => emit('done'), CLOSE_MS)
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
    <Transition name="dialog-fade">
      <div v-if="visible" class="overlay" @click.self="cancel">
        <div class="dialog">
        <!-- 第一页：验证身份 -->
        <template v-if="step === 'verify'">
          <h3 class="title">{{ t('settings.passwordSection') }}</h3>
          <p class="hint">{{ t('settings.verifyHint') }}</p>

          <div class="field">
            <label class="label">{{ t('auth.code') }}</label>
            <div class="code-row">
              <input v-model="code" type="text" :placeholder="t('auth.code')" autocomplete="one-time-code" />
              <button type="button" class="btn ghost" :disabled="sendCooldown > 0" @click="sendCode">
                {{ sendCooldown > 0 ? `${sendCooldown}s` : t('settings.sendCode') }}
              </button>
            </div>
          </div>

          <div class="field">
            <label class="label">{{ t('settings.oldPassword') }}</label>
            <input
              v-model="oldPassword"
              type="password"
              :placeholder="t('settings.oldPassword')"
              autocomplete="current-password"
            />
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
            <button class="btn primary" :disabled="loading" @click="goNext">{{ t('settings.next') }}</button>
          </div>
        </template>

        <!-- 第二页：输入新密码 -->
        <template v-else>
          <h3 class="title">{{ t('settings.passwordSection') }}</h3>

          <div class="field">
            <label class="label">{{ t('settings.newPassword') }}</label>
            <input
              v-model="newPassword"
              type="password"
              :placeholder="t('settings.newPassword')"
              autocomplete="new-password"
            />
          </div>

          <div class="field">
            <label class="label">{{ t('settings.confirmPassword') }}</label>
            <input
              v-model="confirmPassword"
              type="password"
              :placeholder="t('settings.confirmPassword')"
              autocomplete="new-password"
            />
          </div>

          <div class="actions">
            <button class="btn primary" :disabled="loading" @click="changePassword">{{ t('settings.change') }}</button>
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
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.dialog {
  width: min(420px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  padding: 24px;
  border-radius: 16px;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
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
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.label {
  font-size: 14px;
  color: var(--links-color);
}

.field input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  outline: none;
  transition: border-color 0.2s ease;
}

.field input:focus {
  border-color: var(--text-color);
}

.field input[readonly] {
  opacity: 0.7;
  cursor: not-allowed;
}

.code-row {
  display: flex;
  gap: 10px;
}

.code-row input {
  flex: 1;
  min-width: 0;
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

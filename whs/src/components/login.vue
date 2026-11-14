<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import { Eye, EyeOff } from 'lucide-vue-next'
import ForgotPassword from './forgot_password.vue'
import { useAuth } from '../composables/useAuth'
import { sha256 } from '../composables/sha256'
import { copyText } from '../composables/clipboard'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'
import { useTips } from '../composables/useTips'

const emit = defineEmits(['switch-register'])

const { t, locale } = useI18n()
const router = useRouter()
const { setAuth, fetchMe } = useAuth()
const { showTip } = useTips()

// 三段式邮箱：本地部分(字母/数字/_/./-)+ 单个@ + 域名(至少一个点)
const EMAIL_RE = /^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/
const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/

// 'account'：账密登录；'email'：邮箱验证码登录
const mode = ref('account')
const identifier = ref('')
const password = ref('')
const showPassword = ref(false)
const email = ref('')
const code = ref('')
const loading = ref(false)
const sendingCode = ref(false)
const hcaptchaToken = ref('')
const hcaptchaSiteKey = useHcaptchaSiteKey()
const sendCooldown = ref(0)
const showForgot = ref(false)
let cooldownTimer = null

// ---------- 登录二次验证（MFA） ----------
// 第一步账密/邮箱验证通过后，若账号启用了双重验证，后端返回 mfa_required；
// 此时进入第二步，可用「验证器 App 验证码 / 微软账号批准 / 恢复码」三种方式之一完成登录。
const mfaToken = ref('')
const mfaMethods = ref({ totp: false, microsoft: false })
const mfaMode = ref('totp') // 'totp' | 'microsoft' | 'recovery'
const mfaCode = ref('')
const mfaLoading = ref(false)
const mfaStarted = ref(false) // 是否处于第二步

// 微软账号批准（设备码流程）
const msDevice = ref(null) // { challenge_id, user_code, verification_uri, interval }
const msWaiting = ref(false)
const msRemaining = ref(0)
const msSlowDown = ref(false)
let msPollTimer = null
let msCountdownTimer = null

function stopMsTimers() {
  if (msPollTimer) {
    clearInterval(msPollTimer)
    msPollTimer = null
  }
  if (msCountdownTimer) {
    clearInterval(msCountdownTimer)
    msCountdownTimer = null
  }
  msWaiting.value = false
}

const captchaTheme = computed(() => {
  const html = document.documentElement
  if (html.classList.contains('dark')) return 'dark'
  if (html.classList.contains('light')) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
})

function onVerify(token) {
  hcaptchaToken.value = token
}

function onCaptchaExpired() {
  hcaptchaToken.value = ''
  showTip('warning', t('auth.captcha_expired'))
}

function onCaptchaError(err) {
  // hCaptcha 的 error 事件常为瞬时（如网络抖动），组件随后仍可正常使用，
  // 因此这里只清空 token 并记录日志，不弹出误导性的“加载失败”提示。
  hcaptchaToken.value = ''
  console.warn('hCaptcha error:', err)
}

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function submit() {
  loading.value = true
  try {
    let body
    if (mode.value === 'account') {
      if (!identifier.value.trim()) { showTip('warning', t('auth.email_required')); return }
      if (!password.value) { showTip('warning', t('auth.password_required')); return }
      if (!PASSWORD_ASCII_RE.test(password.value)) { showTip('warning', t('auth.password_ascii')); return }
      const passwordHash = await sha256(password.value)
      body = { identifier: identifier.value.trim(), password: passwordHash }
    } else {
      if (!EMAIL_RE.test(email.value.trim())) { showTip('warning', t('auth.email_invalid')); return }
      if (!code.value.trim()) { showTip('warning', t('auth.code_required')); return }
      body = { identifier: email.value.trim(), code: code.value.trim() }
    }

    // 人机验证仅"发送验证码"时需要，登录提交不再要求

    const res = await fetch('/api/user/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json().catch(() => ({}))

    if (res.ok && data.mfa_required) {
      // 第一步通过，进入双重验证第二步
      mfaToken.value = data.mfa_token
      mfaMethods.value = data.methods || { totp: false, microsoft: false }
      mfaMode.value = mfaMethods.value.totp ? 'totp' : 'microsoft'
      mfaCode.value = ''
      password.value = ''
      mfaStarted.value = true
      return
    }

    if (res.ok) {
      finishLogin(data)
      return
    }

    // 账号不存在：切到注册并预填
    if (data.code === 'user_not_found') {
      if (mode.value === 'account') {
        emit('switch-register', { email: identifier.value.trim(), password: password.value })
      } else {
        emit('switch-register', { email: email.value.trim(), code: code.value.trim() })
      }
      return
    }

    showTip('error', localMessage(data))
  } catch(e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}

// 登录成功后的统一收尾：写入登录态并按权限跳转
function finishLogin(data) {
  setAuth(data.token, data.user)
  fetchMe() // 登录成功：刷新公共用户数据（操作变更后统一重新拉取）
  // 权限 < 2（guest/user，尚未通过入服考试）：跳转"加入我们"（考试入口）
  const permission = data.user?.permission ?? 0
  router.push(permission >= 2 ? `/user/${data.user.uid}` : '/joinus')
}

// 返回第一步登录
function resetMfa() {
  stopMsTimers()
  msDevice.value = null
  mfaStarted.value = false
  mfaToken.value = ''
  mfaCode.value = ''
}

// 二次验证：验证器 App 验证码 / 恢复码
async function submitMfa() {
  const value = mfaCode.value.trim()
  if (mfaMode.value === 'totp' && !/^\d{6}$/.test(value)) {
    showTip('warning', t('auth.mfa_code_hint'))
    return
  }
  if (!value) {
    showTip('warning', t('auth.mfa_code_required'))
    return
  }
  mfaLoading.value = true
  try {
    const res = await fetch('/api/user/mfa/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mfa_token: mfaToken.value,
        mode: mfaMode.value,
        code: value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      resetMfa()
      finishLogin(data)
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    mfaLoading.value = false
  }
}

// 二次验证：发起微软账号批准（设备码流程）
async function startMsLogin() {
  if (msWaiting.value) return
  mfaLoading.value = true
  try {
    const res = await fetch('/api/user/mfa/ms/login/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mfa_token: mfaToken.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showTip('error', localMessage(data))
      return
    }
    msDevice.value = data
    msRemaining.value = Number(data.expires_in) || 900
    msSlowDown.value = false
    beginMsPolling(Number(data.interval) || 5)
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    mfaLoading.value = false
  }
}

let msPolling = false

async function pollMsOnce() {
  if (!msDevice.value || !msWaiting.value || msPolling) return
  msPolling = true
  try {
    const res = await fetch('/api/user/mfa/ms/login/poll', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mfa_token: mfaToken.value,
        challenge_id: msDevice.value.challenge_id,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      stopMsTimers()
      showTip('error', localMessage(data))
      msDevice.value = null
      return
    }
    if (data.status === 'success') {
      stopMsTimers()
      msDevice.value = null
      resetMfa()
      finishLogin(data)
      return
    }
    if (data.status === 'slow_down' && !msSlowDown.value) {
      msSlowDown.value = true
      beginMsPolling(Number(msDevice.value.interval || 5) + 5)
      return
    }
    if (data.status === 'declined' || data.status === 'expired' || data.status === 'error') {
      stopMsTimers()
      msDevice.value = null
      showTip('error', t(data.status === 'declined' ? 'auth.mfa_ms_declined' : 'auth.mfa_ms_expired'))
    }
  } catch (e) {
    console.warn(e)
  } finally {
    msPolling = false
  }
}

function beginMsPolling(seconds) {
  stopMsTimers()
  msWaiting.value = true
  msPollTimer = setInterval(pollMsOnce, Math.max(5, seconds) * 1000)
  msCountdownTimer = setInterval(() => {
    msRemaining.value -= 1
    if (msRemaining.value <= 0) {
      stopMsTimers()
      msDevice.value = null
      showTip('error', t('auth.mfa_ms_expired'))
    }
  }, 1000)
  pollMsOnce()
}

async function copyDeviceCode() {
  if (!msDevice.value) return
  const ok = await copyText(msDevice.value.user_code)
  showTip(ok ? 'info' : 'warning', t(ok ? 'auth.mfa_code_copied' : 'auth.mfa_copy_failed'))
}

function openDevicePage() {
  if (msDevice.value?.verification_uri) {
    window.open(msDevice.value.verification_uri, '_blank', 'noopener')
  }
}

// 切换二次验证方式：离开微软批准时停止轮询，避免后台无谓请求
function setMfaMode(next) {
  if (next !== 'microsoft') {
    stopMsTimers()
    msDevice.value = null
  }
  mfaMode.value = next
  mfaCode.value = ''
}

const countdownText = computed(() => {
  const total = Math.max(0, msRemaining.value)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
})

async function sendCode() {
  if (!EMAIL_RE.test(email.value.trim())) {
    showTip('warning', t('auth.email_invalid'))
    return
  }
  // 必须先完成人机验证，才能获取验证码
  if (!hcaptchaToken.value) {
    showTip('warning', t('auth.captcha_required'))
    return
  }
  if (sendCooldown.value > 0 || sendingCode.value) return
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

onUnmounted(() => {
  if (cooldownTimer) {
    clearInterval(cooldownTimer)
    cooldownTimer = null
  }
  stopMsTimers()
})
</script>

<template>
  <div class="login-form">
    <h1 class="form-title">{{ mfaStarted ? t('auth.mfa_title') : t('auth.title') }}</h1>

    <template v-if="!mfaStarted">
    <div class="mode-tabs">
      <button
        type="button"
        :class="{ active: mode === 'account' }"
        @click="mode = 'account'"
      >{{ t('auth.account_mode') }}</button>
      <button
        type="button"
        :class="{ active: mode === 'email' }"
        @click="mode = 'email'"
      >{{ t('auth.email_mode') }}</button>
    </div>

    <form class="form" novalidate @submit.prevent="submit">
      <!-- 账密登录 -->
      <template v-if="mode === 'account'">
        <label class="float-field">
          <input v-model="identifier" type="text" placeholder=" " autocomplete="username" />
          <span class="float-label">{{ t('auth.identifier') }}</span>
        </label>
        <div class="pwd-field">
          <label class="float-field">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              placeholder=" "
              autocomplete="current-password"
            />
            <span class="float-label">{{ t('auth.password') }}</span>
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
      </template>

      <!-- 邮箱验证码登录 -->
      <template v-else>
        <label class="float-field">
          <input v-model="email" type="email" placeholder=" " autocomplete="email" />
          <span class="float-label">{{ t('auth.email') }}</span>
        </label>
        <div class="code-row">
          <label class="float-field">
            <input v-model="code" type="text" placeholder=" " autocomplete="one-time-code" />
            <span class="float-label">{{ t('auth.code') }}</span>
          </label>
          <button type="button" class="send-code" :disabled="sendCooldown > 0 || sendingCode" @click="sendCode">
            <span v-if="sendingCode" class="spinner"></span>
            {{ sendCooldown > 0 ? `${sendCooldown}s` : t('auth.send_code') }}
          </button>
        </div>
      </template>

      <!-- 人机验证码（hCaptcha）：仅邮箱验证码登录模式需要（用于发送验证码） -->
      <div v-if="mode === 'email'" class="h-captcha">
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

      <button type="submit" class="submit" :disabled="loading">
        <span v-if="loading" class="spinner"></span>
        {{ t('auth.login') }}
      </button>
    </form>

    <div class="form-foot" :class="{ centered: mode !== 'account' }">
      <!-- 忘记密码：仅在账密登录模式显示（验证码登录无需密码） -->
      <button v-if="mode === 'account'" type="button" class="forgot-link" @click="showForgot = true">
        {{ t('auth.forgot_password') }}
      </button>
      <button type="button" class="switch-link" @click="emit('switch-register', {})">
        {{ t('auth.go_register') }}
      </button>
    </div>
    </template>

    <!-- 第二步：双重验证 -->
    <div v-else class="mfa-panel">
      <p class="mfa-hint">{{ t('auth.mfa_hint') }}</p>

      <div class="mfa-tabs">
        <button
          v-if="mfaMethods.totp"
          type="button"
          :class="{ active: mfaMode === 'totp' }"
          @click="setMfaMode('totp')"
        >{{ t('auth.mfa_totp_tab') }}</button>
        <button
          v-if="mfaMethods.microsoft"
          type="button"
          :class="{ active: mfaMode === 'microsoft' }"
          @click="setMfaMode('microsoft')"
        >{{ t('auth.mfa_ms_tab') }}</button>
        <button
          type="button"
          :class="{ active: mfaMode === 'recovery' }"
          @click="setMfaMode('recovery')"
        >{{ t('auth.mfa_recovery_tab') }}</button>
      </div>

      <!-- 验证器 App 6 位验证码 -->
      <form v-if="mfaMode === 'totp'" class="form" novalidate @submit.prevent="submitMfa">
        <label class="float-field">
          <input
            v-model="mfaCode"
            class="otp-input"
            type="text"
            inputmode="numeric"
            maxlength="6"
            autocomplete="one-time-code"
            placeholder=" "
          />
          <span class="float-label">{{ t('auth.mfa_code') }}</span>
        </label>
        <p class="mfa-tip">{{ t('auth.mfa_totp_hint') }}</p>
        <button type="submit" class="submit" :disabled="mfaLoading">
          <span v-if="mfaLoading" class="spinner"></span>
          {{ t('auth.mfa_verify') }}
        </button>
      </form>

      <!-- 恢复码 -->
      <form v-else-if="mfaMode === 'recovery'" class="form" novalidate @submit.prevent="submitMfa">
        <label class="float-field">
          <input v-model="mfaCode" type="text" autocomplete="off" placeholder=" " />
          <span class="float-label">{{ t('auth.mfa_recovery_code') }}</span>
        </label>
        <p class="mfa-tip">{{ t('auth.mfa_recovery_hint') }}</p>
        <button type="submit" class="submit" :disabled="mfaLoading">
          <span v-if="mfaLoading" class="spinner"></span>
          {{ t('auth.mfa_verify') }}
        </button>
      </form>

      <!-- 微软账号批准 -->
      <div v-else class="mfa-ms">
        <template v-if="!msDevice">
          <p class="mfa-tip">{{ t('auth.mfa_ms_hint') }}</p>
          <button type="button" class="submit" :disabled="mfaLoading" @click="startMsLogin">
            <span v-if="mfaLoading" class="spinner"></span>
            {{ t('auth.mfa_ms_start') }}
          </button>
        </template>
        <template v-else>
          <p class="mfa-tip">{{ t('auth.mfa_ms_step') }}</p>
          <button type="button" class="device-code" :title="t('auth.mfa_copy')" @click="copyDeviceCode">
            {{ msDevice.user_code }}
          </button>
          <button type="button" class="ms-open" @click="openDevicePage">
            {{ t('auth.mfa_ms_open') }}
          </button>
          <p class="mfa-status">
            <span v-if="msWaiting" class="spinner"></span>
            <span>{{ msWaiting ? t('auth.mfa_ms_waiting') : '' }}</span>
            <span v-if="msWaiting" class="mfa-countdown">{{ countdownText }}</span>
          </p>
          <button type="button" class="switch-link" :disabled="msWaiting" @click="startMsLogin">
            {{ t('auth.mfa_ms_restart') }}
          </button>
        </template>
      </div>

      <div class="form-foot centered">
        <button type="button" class="switch-link" @click="resetMfa">
          {{ t('auth.mfa_back') }}
        </button>
      </div>
    </div>
  </div>

  <ForgotPassword v-if="showForgot" @close="showForgot = false" />
</template>

<style scoped>
.login-form {
  width: min(420px, 92%);
  margin: 120px auto 40px;
  padding: 32px;
  box-sizing: border-box;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

.form-title {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-color);
  text-align: center;
}

.mode-tabs {
  display: flex;
  margin-bottom: 20px;
  border-radius: 999px;
  padding: 4px;
  background: var(--float-bg);
}

.mode-tabs button {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--links-color);
  padding: 8px 0;
  border-radius: 999px;
  cursor: pointer;
  font: inherit;
  transition: all 0.2s ease;
}

.mode-tabs button.active {
  background: var(--card-color);
  color: var(--text-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.code-row {
  display: flex;
  gap: 10px;
}

.send-code {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-shrink: 0;
  padding: 0 16px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  font: inherit;
  transition: color 0.2s ease;
}

.send-code:hover {
  color: var(--text-color);
}

.send-code:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  border-radius: 12px;
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 底部并排：忘记密码（左）与 去注册（右） */
.form-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}

/* 仅剩“去注册”时（邮箱登录模式）居中 */
.form-foot.centered {
  justify-content: center;
}

.switch-link,
.forgot-link {
  border: none;
  background: none;
  color: var(--links-color);
  cursor: pointer;
  font: inherit;
  transition: color 0.2s ease;
}

.forgot-link {
  padding: 0;
}

.switch-link:hover,
.forgot-link:hover {
  color: var(--text-color);
}

/* ---------- 双重验证（第二步） ---------- */
.mfa-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.mfa-hint {
  margin: 0;
  text-align: center;
  font-size: 14px;
  line-height: 1.6;
  color: var(--links-color);
}

.mfa-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 999px;
  background: var(--float-bg);
}

.mfa-tabs button {
  flex: 1;
  padding: 8px 4px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.mfa-tabs button.active {
  background: var(--card-color);
  color: var(--text-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.mfa-tip {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--links-color);
}

/* 6 位数字验证码：等宽、宽字距、居中 */
.otp-input {
  text-align: center;
  font-size: 20px;
  letter-spacing: 0.4em;
  text-indent: 0.4em;
  font-variant-numeric: tabular-nums;
}

.device-code {
  width: 100%;
  padding: 14px 12px;
  border: 1px dashed rgba(148, 163, 184, 0.5);
  border-radius: 12px;
  background: var(--float-bg);
  color: var(--text-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-indent: 0.18em;
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.device-code:hover {
  border-color: var(--text-color);
}

.ms-open {
  width: 100%;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--links-color);
  font: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
}

.ms-open:hover {
  color: var(--text-color);
  border-color: var(--text-color);
}

.mfa-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  min-height: 20px;
  font-size: 13px;
  color: var(--links-color);
}

.mfa-countdown {
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}
</style>

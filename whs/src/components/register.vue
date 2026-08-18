<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import { useAuth } from '../composables/useAuth'
import { sha256 } from '../composables/sha256'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'
import { useTips } from '../composables/useTips'
import UsernameSuggestion from './username_suggestion.vue'
import FullUserInfo from './full_user_info.vue'

const props = defineProps({
  prefill: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['switch-login'])

const { t, locale } = useI18n()
const router = useRouter()
const { setAuth, fetchMe } = useAuth()
const { showTip } = useTips()

// 三段式邮箱：本地部分(字母/数字/_/./-)+ 单个@ + 域名(至少一个点)
const EMAIL_RE = /^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/
const USERNAME_RE = /^[a-zA-Z0-9_]+$/
const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/

// 编排步骤：register / suggestion / full_info
const step = ref('register')

const email = ref('')
const username = ref('')
const code = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const hcaptchaToken = ref('')
const hcaptchaSiteKey = useHcaptchaSiteKey()
const sendCooldown = ref(0)
let cooldownTimer = null

const suggestionBase = ref('')
const registeredUid = ref(null)

// hCaptcha 主题跟随站点亮/暗色
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

watch(() => props.prefill, (p) => {
  if (!p) return
  if (p.email) email.value = p.email
  if (p.password) {
    password.value = p.password
    confirmPassword.value = p.password
  }
  if (p.code) code.value = p.code
}, { immediate: true, deep: true })

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

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
  if (sendCooldown.value > 0) return
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
}

onUnmounted(() => {
  if (cooldownTimer) {
    clearInterval(cooldownTimer)
    cooldownTimer = null
  }
})

// 真正发起注册请求；成功则进入 full_info 步骤
async function doRegister() {
  const passwordHash = await sha256(password.value)
  const res = await fetch('/api/user/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: email.value.trim(),
      username: username.value.trim(),
      code: code.value.trim(),
      password: passwordHash,
      hcaptcha_response: hcaptchaToken.value,
    }),
  })
  const data = await res.json().catch(() => ({}))
  if (res.ok) {
    setAuth(data.token, { uid: data.uid })
    fetchMe() // 注册成功：拉取完整用户信息填充公共变量（注册响应只有 uid）
    registeredUid.value = data.uid
    step.value = 'full_info'
    return true
  }
  showTip('error', localMessage(data))
  return false
}

async function submit() {
  loading.value = true
  try {
    if (!EMAIL_RE.test(email.value.trim())) { showTip('warning', t('auth.email_invalid')); return }
    if (!USERNAME_RE.test(username.value.trim())) { showTip('warning', t('auth.username_invalid')); return }
    if (!code.value.trim()) { showTip('warning', t('auth.code_required')); return }
    if (!password.value) { showTip('warning', t('auth.password_required')); return }
    if (!PASSWORD_ASCII_RE.test(password.value)) { showTip('warning', t('auth.password_ascii')); return }
    if (password.value !== confirmPassword.value) { showTip('warning', t('auth.password_mismatch')); return }
    if (!hcaptchaToken.value) { showTip('warning', t('auth.captcha_required')); return }

    // 注册前先查重（避免消耗验证码 / hCaptcha）
    const checkRes = await fetch(`/api/user/username_exists?username=${encodeURIComponent(username.value.trim())}`)
    const checkData = await checkRes.json().catch(() => ({}))
    if (checkRes.ok && checkData.exists) {
      suggestionBase.value = username.value.trim()
      step.value = 'suggestion'
      return
    }

    await doRegister()
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}

async function onSuggestionConfirm(chosenUsername) {
  username.value = chosenUsername
  loading.value = true
  try {
    await doRegister()
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="register-form">
    <Transition name="step" mode="out-in">
      <div v-if="step === 'register'" key="register">
        <h1 class="form-title">{{ t('auth.register_title') }}</h1>

      <form class="form" novalidate @submit.prevent="submit">
        <input v-model="email" type="email" :placeholder="t('auth.email')" autocomplete="email" />
        <input v-model="username" type="text" :placeholder="t('register.username_placeholder')" autocomplete="username" />

        <div class="code-row">
          <input v-model="code" type="text" :placeholder="t('auth.code')" autocomplete="one-time-code" />
          <button type="button" class="send-code" :disabled="sendCooldown > 0" @click="sendCode">
            {{ sendCooldown > 0 ? `${sendCooldown}s` : t('auth.send_code') }}
          </button>
        </div>

        <input v-model="password" type="password" :placeholder="t('auth.password')" autocomplete="new-password" />
        <input v-model="confirmPassword" type="password" :placeholder="t('auth.confirm_password')" autocomplete="new-password" />

        <!-- 人机验证码（hCaptcha 官方 Vue 组件） -->
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

        <button type="submit" class="submit" :disabled="loading">{{ t('auth.register') }}</button>
      </form>

        <button type="button" class="switch-link" @click="emit('switch-login')">
          {{ t('auth.go_login') }}
        </button>
      </div>

      <UsernameSuggestion
        v-else-if="step === 'suggestion'"
        key="suggestion"
        :base="suggestionBase"
        @confirm="onSuggestionConfirm"
        @back="step = 'register'"
      />

      <FullUserInfo v-else key="full_info" :uid="registeredUid" />
    </Transition>
  </div>
</template>

<style scoped>
.register-form {
  width: min(420px, 92%);
  margin: 100px auto 40px;
  padding: 32px;
  box-sizing: border-box;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

/* 步骤切换动画：弹出 + 淡入 */
.step-enter-active,
.step-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.step-enter-from,
.step-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.98);
}

.form-title {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-color);
  text-align: center;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form input {
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

.form input:focus {
  border-color: var(--text-color);
}

.code-row {
  display: flex;
  gap: 10px;
}

.code-row input {
  flex: 1;
}

.send-code {
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

.h-captcha {
  width: 100%;
}

.h-captcha :deep(iframe) {
  width: 100% !important;
}

.submit {
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

.switch-link {
  margin-top: 16px;
  width: 100%;
  border: none;
  background: none;
  color: var(--links-color);
  cursor: pointer;
  font: inherit;
  transition: color 0.2s ease;
}

.switch-link:hover {
  color: var(--text-color);
}
</style>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import { useAuth } from '../composables/useAuth'
import { sha256 } from '../utils/sha256'

const emit = defineEmits(['switch-register'])

const { t, locale } = useI18n()
const router = useRouter()
const { setAuth } = useAuth()

const EMAIL_RE = /^[a-zA-Z0-9_@.-]+$/
const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/

// 'account'：账密登录；'email'：邮箱验证码登录
const mode = ref('account')
const identifier = ref('')
const password = ref('')
const email = ref('')
const code = ref('')
const errorMsg = ref('')
const loading = ref(false)
const hcaptchaToken = ref('')

const HCAPTCHA_SITE_KEY = '8f00495e-ff6c-49c8-8f92-0570bd562674'

const captchaTheme = computed(() => {
  const html = document.documentElement
  if (html.classList.contains('dark')) return 'dark'
  if (html.classList.contains('light')) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
})

function onVerify(token) {
  hcaptchaToken.value = token
}

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function submit() {
  errorMsg.value = ''
  loading.value = true
  try {
    let body
    if (mode.value === 'account') {
      if (!identifier.value.trim()) { errorMsg.value = t('auth.email_required'); return }
      if (!password.value) { errorMsg.value = t('auth.password_required'); return }
      if (!PASSWORD_ASCII_RE.test(password.value)) { errorMsg.value = t('auth.password_ascii'); return }
      const passwordHash = await sha256(password.value)
      body = { identifier: identifier.value.trim(), password: passwordHash }
    } else {
      if (!EMAIL_RE.test(email.value.trim())) { errorMsg.value = t('auth.email_invalid'); return }
      if (!code.value.trim()) { errorMsg.value = t('auth.code_required'); return }
      body = { identifier: email.value.trim(), code: code.value.trim() }
    }

    if (!hcaptchaToken.value) { errorMsg.value = t('auth.captcha_required'); return }
    body.hcaptcha_response = hcaptchaToken.value

    const res = await fetch('/api/user/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json().catch(() => ({}))

    if (res.ok) {
      setAuth(data.token, data.user)
      router.push(`/user/${data.user.uid}`)
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

    errorMsg.value = localMessage(data)
  } catch(e) {
    errorMsg.value = t('auth.request_failed')
    console.warn(e)
  } finally {
    loading.value = false
  }
}

async function sendCode() {
  errorMsg.value = ''
  if (!EMAIL_RE.test(email.value.trim())) {
    errorMsg.value = t('auth.email_invalid')
    return
  }
  const res = await fetch('/api/user/send_code', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.value.trim() }),
  })
  const data = await res.json().catch(() => ({}))
  if (res.ok && data.dev_code) {
    // mock 阶段：后端把验证码回传，自动填入方便调试
    code.value = data.dev_code
  } else {
    errorMsg.value = localMessage(data)
  }
}
</script>

<template>
  <div class="login-form">
    <h1 class="form-title">{{ t('auth.title') }}</h1>

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

    <form class="form" @submit.prevent="submit">
      <!-- 账密登录 -->
      <template v-if="mode === 'account'">
        <input
          v-model="identifier"
          type="text"
          :placeholder="t('auth.identifier')"
          autocomplete="username"
        />
        <input
          v-model="password"
          type="password"
          :placeholder="t('auth.password')"
          autocomplete="current-password"
        />
      </template>

      <!-- 邮箱验证码登录 -->
      <template v-else>
        <input v-model="email" type="email" :placeholder="t('auth.email')" autocomplete="email" />
        <div class="code-row">
          <input v-model="code" type="text" :placeholder="t('auth.code')" autocomplete="one-time-code" />
          <button type="button" class="send-code" @click="sendCode">{{ t('auth.send_code') }}</button>
        </div>
      </template>

      <!-- 人机验证码（hCaptcha 官方 Vue 组件） -->
      <div class="h-captcha">
        <VueHcaptcha :sitekey="HCAPTCHA_SITE_KEY" :theme="captchaTheme" @verify="onVerify" />
      </div>

      <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

      <button type="submit" class="submit" :disabled="loading">
        {{ t('auth.login_register') }}
      </button>
    </form>

    <button type="button" class="switch-link" @click="emit('switch-register', {})">
      {{ t('auth.go_register') }}
    </button>
  </div>
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
  background: var(--btn-hover);
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

.error {
  margin: 0;
  color: #e5484d;
  font-size: 14px;
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

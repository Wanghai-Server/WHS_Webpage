<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import { User } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { sha256 } from '../utils/sha256'

const props = defineProps({
  prefill: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['switch-login'])

const { t, locale } = useI18n()
const router = useRouter()
const { setAuth } = useAuth()

const EMAIL_RE = /^[a-zA-Z0-9_@.-]+$/
const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/
const HCAPTCHA_SITE_KEY = '8f00495e-ff6c-49c8-8f92-0570bd562674'

const email = ref('')
const code = ref('')
const password = ref('')
const avatarFile = ref(null)
const avatarPreview = ref('')
const errorMsg = ref('')
const loading = ref(false)
const hcaptchaToken = ref('')

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

watch(() => props.prefill, (p) => {
  if (!p) return
  if (p.email) email.value = p.email
  if (p.password) password.value = p.password
  if (p.code) code.value = p.code
}, { immediate: true, deep: true })

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

function onFileChange(event) {
  const f = event.target.files && event.target.files[0]
  if (!f) return
  avatarFile.value = f
  avatarPreview.value = URL.createObjectURL(f)
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
    code.value = data.dev_code // mock 阶段自动填入
  } else {
    errorMsg.value = localMessage(data)
  }
}

async function submit() {
  errorMsg.value = ''
  loading.value = true
  try {
    if (!EMAIL_RE.test(email.value.trim())) { errorMsg.value = t('auth.email_invalid'); return }
    if (!code.value.trim()) { errorMsg.value = t('auth.code_required'); return }
    if (!password.value) { errorMsg.value = t('auth.password_required'); return }
    if (!PASSWORD_ASCII_RE.test(password.value)) { errorMsg.value = t('auth.password_ascii'); return }
    if (!hcaptchaToken.value) { errorMsg.value = t('auth.captcha_required'); return }

    const passwordHash = await sha256(password.value)

    const res = await fetch('/api/user/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.value.trim(),
        code: code.value.trim(),
        password: passwordHash,
        hcaptcha_response: hcaptchaToken.value,
      }),
    })
    const data = await res.json().catch(() => ({}))

    if (res.ok) {
      setAuth(data.token, { uid: data.uid })
      // 两步：注册拿到 uid 后再上传头像
      if (avatarFile.value) {
        const fd = new FormData()
        fd.append('file', avatarFile.value)
        await fetch(`/api/user/${data.uid}/avatar`, { method: 'POST', body: fd })
      }
      router.push('/joinus')
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

</script>

<template>
  <div class="register-form">
    <h1 class="form-title">{{ t('auth.register_title') }}</h1>

    <form class="form" @submit.prevent="submit">
      <!-- 上传头像（可选，放在 4 个输入框上方） -->
      <label class="avatar-upload">
        <input type="file" accept="image/png,image/jpeg,image/webp,image/x-icon" @change="onFileChange" />
        <img v-if="avatarPreview" :src="avatarPreview" class="avatar-preview" alt="avatar" />
        <User v-else :size="30" class="avatar-icon" />
        <span class="avatar-label">{{ t('auth.upload_avatar') }}</span>
      </label>

      <input v-model="email" type="email" :placeholder="t('auth.email')" autocomplete="email" />

      <div class="code-row">
        <input v-model="code" type="text" :placeholder="t('auth.code')" autocomplete="one-time-code" />
        <button type="button" class="send-code" @click="sendCode">{{ t('auth.send_code') }}</button>
      </div>

      <input v-model="password" type="password" :placeholder="t('auth.password')" autocomplete="new-password" />

      <!-- 人机验证码（hCaptcha 官方 Vue 组件） -->
      <div class="h-captcha">
        <VueHcaptcha :sitekey="HCAPTCHA_SITE_KEY" :theme="captchaTheme" @verify="onVerify" />
      </div>

      <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

      <button type="submit" class="submit" :disabled="loading">{{ t('auth.register') }}</button>
    </form>

    <button type="button" class="switch-link" @click="emit('switch-login')">
      {{ t('auth.go_login') }}
    </button>
  </div>
</template>

<style scoped>
.register-form {
  width: min(420px, 92%);
  margin: 100px auto 40px;
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

.avatar-upload {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  margin: 0 auto;
  border-radius: 999px;
  overflow: hidden;
  border: 1px dashed rgba(148, 163, 184, 0.35);
  color: var(--links-color);
  cursor: pointer;
}

.avatar-upload input {
  display: none;
}

.avatar-icon {
  color: var(--links-color);
}

.avatar-preview {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-label {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2;
  padding: 3px 0;
  font-size: 11px;
  text-align: center;
  color: #ffffff;
  background: rgba(0, 0, 0, 0.45);
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

.h-captcha {
  width: 100%;
}

.h-captcha :deep(iframe) {
  width: 100% !important;
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

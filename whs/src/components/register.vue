<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Eye, EyeOff } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { sha256 } from '../composables/sha256'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'
import { useTips } from '../composables/useTips'
import { EMAIL_RE, useEmailCode } from '../composables/useEmailCode'
import { usePasswordStrength } from '../composables/usePasswordStrength'
import HcaptchaBox from './hcaptcha_box.vue'
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

const USERNAME_RE = /^[a-zA-Z0-9_]+$/
const PASSWORD_ASCII_RE = /^[\x00-\x7F]+$/

// 编排步骤：email（邮箱+验证码+人机验证）→ account（用户名+密码）→ suggestion / full_info
const step = ref('email')

// 第一步
const email = ref('')
const code = ref('')
const hcaptchaToken = ref('')
const hcaptchaSiteKey = useHcaptchaSiteKey()
const captchaRef = ref(null)
const ticket = ref('')
const ticketEmail = ref('')
const verifying = ref(false)

// 第二步
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
// 注册页两个密码框共用一个显示/隐藏按钮（按钮在“确认密码”框内）
const showPassword = ref(false)
const loading = ref(false)

const { sending: sendingCode, cooldown: sendCooldown, send: sendEmailCode } = useEmailCode()
const {
  rules: passwordRules,
  hardRules: passwordHardRules,
  level: passwordLevel,
  percent: strengthPercent,
  touch: touchPasswordStrength,
} = usePasswordStrength(password)

const suggestionBase = ref('')
const registeredUid = ref(null)

// hCaptcha 主题跟随站点亮/暗色
const captchaTheme = computed(() => {
  const html = document.documentElement
  if (html.classList.contains('dark')) return 'dark'
  if (html.classList.contains('light')) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
})

const strengthClass = computed(() => passwordLevel.value || 'none')
const strengthText = computed(() => {
  if (!passwordLevel.value) return '—'
  return t(`register.strength_${passwordLevel.value}`)
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
  if (p.code) code.value = String(p.code).replace(/\D/g, '').slice(0, 6)
}, { immediate: true, deep: true })

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function sendCode() {
  await sendEmailCode(email.value, {
    hcaptchaToken: hcaptchaToken.value,
    resetCaptcha: () => {
      // token 一次性，发送成功后清空本地 token 并重置控件
      hcaptchaToken.value = ''
      captchaRef.value?.reset()
    },
  })
}

// ---- 验证码输入：只允许数字，允许粘贴（粘贴时剥离非数字） ----
function sanitizeCode(value) {
  return String(value || '').replace(/\D/g, '').slice(0, 6)
}

function onCodeInput(event) {
  const el = event.target
  const next = sanitizeCode(el.value)
  if (el.value !== next) el.value = next
  code.value = next
}

function onCodeKeydown(event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return
  if (event.key.length === 1 && !/[0-9]/.test(event.key)) {
    event.preventDefault()
  }
}

function onCodePaste(event) {
  event.preventDefault()
  const el = event.target
  const pasted = sanitizeCode(event.clipboardData?.getData('text') || '')
  if (!pasted) return
  const start = el.selectionStart ?? el.value.length
  const end = el.selectionEnd ?? el.value.length
  const next = sanitizeCode(el.value.slice(0, start) + pasted + el.value.slice(end))
  el.value = next
  code.value = next
  const cursor = Math.min(start + pasted.length, next.length)
  nextTick(() => el.setSelectionRange(cursor, cursor))
}

// ---- 第一步 → 第二步：校验邮箱验证码并换取注册凭证 ----
async function goAccount() {
  if (!EMAIL_RE.test(email.value.trim())) {
    showTip('warning', t('auth.email_invalid'))
    return
  }
  // 返回上一步后凭证仍有效：邮箱未变时无需重新输码
  if (ticket.value && ticketEmail.value === email.value.trim()) {
    step.value = 'account'
    return
  }
  if (!code.value.trim()) {
    showTip('warning', t('auth.code_required'))
    return
  }
  verifying.value = true
  try {
    const res = await fetch('/api/user/register/email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value.trim(), code: code.value.trim() }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showTip('error', localMessage(data))
      return
    }
    ticket.value = data.ticket
    ticketEmail.value = data.email
    code.value = ''
    step.value = 'account'
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    verifying.value = false
  }
}

function backToEmail() {
  step.value = 'email'
}

// ---- 第二步：用户名 + 密码 ----
async function submitAccount() {
  touchPasswordStrength()
  if (!USERNAME_RE.test(username.value.trim())) {
    showTip('warning', t('auth.username_invalid'))
    return
  }
  if (!password.value) {
    showTip('warning', t('auth.password_required'))
    return
  }
  if (!PASSWORD_ASCII_RE.test(password.value)) {
    showTip('warning', t('auth.password_ascii'))
    return
  }
  // 提交前再次校验强度：后端只能看到哈希，强度只能由前端判断
  if (!passwordHardRules.value.every((rule) => rule.ok)) {
    showTip('warning', t('register.password_weak'))
    return
  }
  if (password.value !== confirmPassword.value) {
    showTip('warning', t('auth.password_mismatch'))
    return
  }
  if (!ticket.value) {
    step.value = 'email'
    showTip('error', t('register.ticket_expired'))
    return
  }

  loading.value = true
  try {
    // 注册前先查重（避免创建失败）
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

// 真正发起注册请求；成功则进入 full_info 步骤
async function doRegister() {
  const passwordHash = await sha256(password.value)
  const res = await fetch('/api/user/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ticket: ticket.value,
      username: username.value.trim(),
      password: passwordHash,
    }),
  })
  const data = await res.json().catch(() => ({}))
  if (res.ok) {
    setAuth(data.token, { uid: data.uid })
    fetchMe() // 注册成功：拉取完整用户信息填充公共变量（注册响应只有 uid）
    registeredUid.value = data.uid
    ticket.value = ''
    ticketEmail.value = ''
    step.value = 'full_info'
    return true
  }
  if (data.code === 'register_ticket_invalid') {
    // 凭证失效：回到第一步重新验证（旧验证码已被消费，需重新发送）
    ticket.value = ''
    ticketEmail.value = ''
    code.value = ''
    step.value = 'email'
  }
  showTip('error', localMessage(data))
  return false
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
      <!-- 第一步：邮箱 + 验证码 + 人机验证 -->
      <div v-if="step === 'email'" key="email">
        <h1 class="form-title">{{ t('auth.register_title') }}</h1>

        <form class="form" novalidate @submit.prevent="goAccount">
          <label class="float-field">
            <input v-model="email" type="email" placeholder=" " autocomplete="email" />
            <span class="float-label">{{ t('auth.email') }}</span>
          </label>

          <div class="code-row">
            <label class="float-field">
              <input
                :value="code"
                type="text"
                inputmode="numeric"
                placeholder=" "
                autocomplete="one-time-code"
                maxlength="6"
                @input="onCodeInput"
                @keydown="onCodeKeydown"
                @paste="onCodePaste"
              />
              <span class="float-label">{{ t('auth.code') }}</span>
            </label>
            <button type="button" class="send-code" :disabled="sendCooldown > 0 || sendingCode" @click="sendCode">
              <span v-if="sendingCode" class="spinner"></span>
              {{ sendCooldown > 0 ? `${sendCooldown}s` : t('auth.send_code') }}
            </button>
          </div>

          <!-- 人机验证码（hCaptcha 官方 Vue 组件，自适应容器宽度） -->
          <div class="h-captcha">
            <HcaptchaBox
              v-if="hcaptchaSiteKey"
              ref="captchaRef"
              :sitekey="hcaptchaSiteKey"
              :theme="captchaTheme"
              @verify="onVerify"
              @expired="onCaptchaExpired"
              @error="onCaptchaError"
            />
          </div>

          <button type="submit" class="submit" :disabled="verifying">
            <span v-if="verifying" class="spinner"></span>
            {{ t('register.next') }}
          </button>
        </form>

        <button type="button" class="switch-link" @click="emit('switch-login')">
          {{ t('auth.go_login') }}
        </button>
      </div>

      <!-- 第二步：用户名 + 密码（含强度提示） -->
      <div v-else-if="step === 'account'" key="account">
        <h1 class="form-title">{{ t('auth.register_title') }}</h1>

        <form class="form" novalidate @submit.prevent="submitAccount">
          <label class="float-field">
            <input v-model="username" type="text" placeholder=" " autocomplete="username" />
            <span class="float-label">{{ t('register.username_placeholder') }}</span>
          </label>

          <label class="float-field">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              placeholder=" "
              autocomplete="new-password"
              @blur="touchPasswordStrength"
            />
            <span class="float-label">{{ t('auth.password') }}</span>
          </label>
          <div class="pwd-field">
            <label class="float-field">
              <input
                v-model="confirmPassword"
                :type="showPassword ? 'text' : 'password'"
                placeholder=" "
                autocomplete="new-password"
                @blur="touchPasswordStrength"
              />
              <span class="float-label">{{ t('auth.confirm_password') }}</span>
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

          <!-- 当前强度：较短进度条 + 低/中/高（未满足三条要求时不计算等级） -->
          <div class="pwd-strength" :class="`strength-${strengthClass}`">
            <div class="pwd-strength-track">
              <span class="pwd-strength-fill" :style="{ width: `${strengthPercent}%` }"></span>
            </div>
            <span class="pwd-strength-label">{{ strengthText }}</span>
          </div>

          <!-- 三条硬性要求：默认灰色，满足变绿，失焦后未满足标红 -->
          <ul class="pwd-rules">
            <li
              v-for="rule in passwordRules"
              :key="rule.key"
              :class="[`rule-${rule.state}`, { 'rule-optional': rule.optional }]"
            >
              <span class="rule-dot" aria-hidden="true"></span>
              <span>{{ t(`register.rule_${rule.key}`) }}</span>
            </li>
          </ul>

          <button type="submit" class="submit" :disabled="loading">
            <span v-if="loading" class="spinner"></span>
            {{ t('auth.register') }}
          </button>
        </form>

        <div class="form-actions">
          <button type="button" class="switch-link" @click="backToEmail">{{ t('register.back') }}</button>
          <button type="button" class="switch-link" @click="emit('switch-login')">{{ t('auth.go_login') }}</button>
        </div>
      </div>

      <UsernameSuggestion
        v-else-if="step === 'suggestion'"
        key="suggestion"
        :base="suggestionBase"
        :loading="loading"
        @confirm="onSuggestionConfirm"
        @back="step = 'account'"
      />

      <FullUserInfo v-else key="full_info" :uid="registeredUid" />
    </Transition>
  </div>
</template>

<style scoped>
.register-form {
  /* 半透明毛玻璃卡片：浮动标签底色跟随卡片背景，避免白色补丁 */
  --float-label-bg: var(--navbar-bg);
  width: min(420px, 92%);
  margin: 100px auto 40px;
  padding: 32px;
  box-sizing: border-box;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
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

.h-captcha {
  width: 100%;
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

.form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}

.form-actions .switch-link {
  width: auto;
  margin-top: 0;
}

/* 密码强度：短进度条 + 等级文字 */
.pwd-strength {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pwd-strength-track {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: var(--float-bg);
  overflow: hidden;
}

.pwd-strength-fill {
  display: block;
  height: 100%;
  width: 0;
  border-radius: 999px;
  background: var(--links-color);
  transition: width 0.2s ease, background-color 0.2s ease;
}

.pwd-strength-label {
  min-width: 2.5em;
  font-size: 12px;
  line-height: 1;
  text-align: right;
  color: var(--links-color);
}

.strength-low .pwd-strength-fill {
  background: #e5484d;
}

.strength-low .pwd-strength-label {
  color: #e5484d;
}

.strength-middle .pwd-strength-fill {
  background: #f59e0b;
}

.strength-middle .pwd-strength-label {
  color: #f59e0b;
}

.strength-high .pwd-strength-fill {
  background: #22c55e;
}

.strength-high .pwd-strength-label {
  color: #22c55e;
}

/* 三条硬性要求 */
.pwd-rules {
  list-style: none;
  margin: -4px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--links-color);
}

.pwd-rules li {
  display: flex;
  align-items: center;
  gap: 6px;
  transition: color 0.2s ease;
}

.rule-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.rule-ok {
  color: #22c55e;
}

.rule-error {
  color: #e5484d;
}

/* 特殊字符为可选项：只影响强度等级，不拦截提交 */
.rule-optional {
  opacity: 0.85;
}
</style>

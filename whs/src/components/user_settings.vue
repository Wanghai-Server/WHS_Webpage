<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { Pencil, UserRound, Trash2 } from 'lucide-vue-next'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'
import ChangePassword from './change_password.vue'
import CancelAccount from './cancel_account.vue'
import ManageAccounts from './manage_accounts.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'

const props = defineProps({
  user: { type: Object, required: true },
  focusProfileKey: { type: Number, default: 0 },
})
const emit = defineEmits(['saved'])

const { t, locale } = useI18n()
const { state: authState, fetchMe } = useAuth()
const { showTip } = useTips()
const hcaptchaSiteKey = useHcaptchaSiteKey()

const EMAIL_RE = /^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/

// 基本资料（username / player_name 注册与加入时固定，不可修改）
const fullname = ref(props.user.fullname || '')
const gender = ref(props.user.gender ?? null)
const year = ref(props.user.birthday_year ?? null)
const month = ref(props.user.birthday_month ?? null)
const day = ref(props.user.birthday_day ?? null)

// 简介
const profile = ref(props.user.profile || '')
const profileTextarea = ref(null)

// 对话框开关（头像 / 邮箱 / 密码）
const showAvatarDialog = ref(false)
const showEmailDialog = ref(false)
const showPasswordDialog = ref(false)
const showCancelDialog = ref(false)

// 头像对话框
const avatarFile = ref(null)
const avatarPreview = ref('')
const savingAvatar = ref(false)

// 当前头像（未选择新文件时默认展示）
const currentAvatar = computed(() =>
  props.user.avatar ? `/api/user/${props.user.uid}/avatar` : ''
)

// 邮箱对话框
const newEmail = ref(props.user.email || '')
const emailCode = ref('')
const emailCooldown = ref(0)
const savingEmail = ref(false)
const emailCaptchaToken = ref('')
let emailTimer = null

// 保存状态
const savingBasic = ref(false)
const savingProfile = ref(false)
const emailSendingCode = ref(false)

const currentYear = new Date().getFullYear()
const years = computed(() => {
  const arr = []
  for (let y = currentYear; y >= 1920; y--) arr.push(y)
  return arr
})
const months = Array.from({ length: 12 }, (_, i) => i + 1)
const days = Array.from({ length: 31 }, (_, i) => i + 1)

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

// 生日级联
function onYearChange() {
  if (year.value === null) {
    month.value = null
    day.value = null
  } else if (month.value === null) {
    day.value = null
  }
}

function onMonthChange() {
  if (month.value === null) day.value = null
}

function focusProfile() {
  nextTick(() => {
    profileTextarea.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    profileTextarea.value?.focus()
  })
}

watch(
  () => props.focusProfileKey,
  (k) => {
    if (k > 0) focusProfile()
  }
)
// ESC 关闭当前打开的对话框（密码对话框由 change_password.vue 自身处理）
function handleKeydown(e) {
  if (e.key !== 'Escape') return
  if (showAvatarDialog.value) {
    showAvatarDialog.value = false
  } else if (showEmailDialog.value) {
    showEmailDialog.value = false
  }
}

onMounted(() => {
  if (props.focusProfileKey > 0) focusProfile()
  document.addEventListener('keydown', handleKeydown)
})

// 撤销基本资料修改（恢复为服务器当前值）
function revertBasic() {
  fullname.value = props.user.fullname || ''
  gender.value = props.user.gender ?? null
  year.value = props.user.birthday_year ?? null
  month.value = props.user.birthday_month ?? null
  day.value = props.user.birthday_day ?? null
  showTip('info', t('settings.undone'))
}

// 撤销简介修改（恢复为服务器当前值）
function revertProfile() {
  profile.value = props.user.profile || ''
  showTip('info', t('settings.undone'))
}

// 是否有未保存的更改（决定撤销按钮是否渲染）
const profileDirty = computed(() => profile.value !== (props.user.profile || ''))

const basicDirty = computed(() =>
  fullname.value !== (props.user.fullname || '') ||
  gender.value !== (props.user.gender ?? null) ||
  year.value !== (props.user.birthday_year ?? null) ||
  month.value !== (props.user.birthday_month ?? null) ||
  day.value !== (props.user.birthday_day ?? null)
)

// 保存基本资料
async function saveBasic() {
  savingBasic.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/info`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        fullname: fullname.value.trim(),
        gender: gender.value,
        birthday_year: year.value,
        birthday_month: month.value,
        birthday_day: day.value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.basicSaved'))
      fetchMe() // 基本资料变更：刷新公共用户数据
      emit('saved')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    savingBasic.value = false
  }
}

// 保存简介
async function saveProfile() {
  savingProfile.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/profile`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ profile: profile.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.profileSaved'))
      fetchMe() // 简介变更：刷新公共用户数据
      emit('saved')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    savingProfile.value = false
  }
}

// ---------- 头像对话框 ----------

function onAvatarChange(event) {
  const f = event.target.files && event.target.files[0]
  if (!f) return
  avatarFile.value = f
  avatarPreview.value = URL.createObjectURL(f)
}

async function uploadAvatar() {
  if (!avatarFile.value) {
    showTip('warning', t('auth.upload_avatar'))
    return
  }
  savingAvatar.value = true
  try {
    const fd = new FormData()
    fd.append('file', avatarFile.value)
    const res = await fetch(`/api/user/${props.user.uid}/avatar`, {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.avatarSaved'))
      fetchMe() // 头像变更：刷新公共用户数据（导航栏头像即时更新）
      showAvatarDialog.value = false
      emit('saved')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    savingAvatar.value = false
  }
}

// ---------- 邮箱对话框 ----------

function onEmailCaptchaVerify(token) {
  emailCaptchaToken.value = token
}

function onEmailCaptchaExpired() {
  emailCaptchaToken.value = ''
  showTip('warning', t('auth.captcha_expired'))
}

function onEmailCaptchaError() {
  emailCaptchaToken.value = ''
  console.warn('hCaptcha error')
}

async function sendEmailCode() {
  if (!EMAIL_RE.test(newEmail.value.trim())) {
    showTip('warning', t('auth.email_invalid'))
    return
  }
  // 必须先完成人机验证，才能获取验证码
  if (!emailCaptchaToken.value) {
    showTip('warning', t('auth.captcha_required'))
    return
  }
  if (emailCooldown.value > 0 || emailSendingCode.value) return
  emailSendingCode.value = true
  try {
    const res = await fetch('/api/user/send_code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: newEmail.value.trim(), locale: locale.value, hcaptcha_response: emailCaptchaToken.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok && data.success) {
      showTip('info', t('auth.code_sent'))
      emailCooldown.value = 60
      if (emailTimer) clearInterval(emailTimer)
      emailTimer = setInterval(() => {
        emailCooldown.value -= 1
        if (emailCooldown.value <= 0) {
          clearInterval(emailTimer)
          emailTimer = null
        }
      }, 1000)
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    emailSendingCode.value = false
  }
}

async function changeEmail() {
  if (!EMAIL_RE.test(newEmail.value.trim())) {
    showTip('warning', t('auth.email_invalid'))
    return
  }
  if (newEmail.value.trim() === props.user.email) {
    showTip('warning', t('settings.emailSame'))
    return
  }
  if (!emailCode.value.trim()) {
    showTip('warning', t('auth.code_required'))
    return
  }
  savingEmail.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/email`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        email: newEmail.value.trim(),
        code: emailCode.value.trim(),
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.emailSaved'))
      fetchMe() // 邮箱变更：刷新公共用户数据
      emailCode.value = ''
      emailCaptchaToken.value = ''
      showEmailDialog.value = false
      emit('saved')
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    savingEmail.value = false
  }
}

// ---------- 密码对话框（change_password.vue 处理） ----------

function onPasswordDone() {
  // 密码变更的 fetchMe 已在 change_password.vue 成功后执行，这里只负责关闭弹窗
  showPasswordDialog.value = false
  emit('saved')
}

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (emailTimer) {
    clearInterval(emailTimer)
    emailTimer = null
  }
})
</script>

<template>
  <section class="user-settings">
    <!-- 个人简介 -->
    <div class="settings-card load-in">
      <h2 class="card-title">{{ t('settings.profile') }}</h2>
      <textarea
        ref="profileTextarea"
        v-model="profile"
        class="profile-input"
        :placeholder="t('settings.profilePlaceholder')"
      ></textarea>
      <div class="card-actions">
        <button v-if="profileDirty" class="btn ghost" :disabled="savingProfile" @click="revertProfile">
          {{ t('settings.undo') }}
        </button>
        <button class="btn primary" :disabled="savingProfile" @click="saveProfile">
          <span v-if="savingProfile" class="spinner"></span>
          {{ t('settings.saveProfile') }}
        </button>
      </div>
    </div>

    <!-- 基本资料（username / player_name 固定不可改） -->
    <div class="settings-card load-in" style="--load-delay: 80ms">
      <h2 class="card-title">{{ t('settings.basic') }}</h2>
      <div class="field">
        <label class="label">{{ t('settings.fullname') }}</label>
        <input v-model="fullname" type="text" :placeholder="t('settings.fullname')" />
      </div>
      <div class="field">
        <label class="label">{{ t('settings.gender') }}</label>
        <select v-model="gender">
          <option :value="null">{{ t('settings.none') }}</option>
          <option value="male">{{ t('settings.male') }}</option>
          <option value="female">{{ t('settings.female') }}</option>
        </select>
      </div>
      <div class="field">
        <label class="label">{{ t('settings.birthday') }}</label>
        <div class="birthday-row">
          <select v-model="year" @change="onYearChange">
            <option :value="null">{{ t('settings.none') }}</option>
            <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
          </select>
          <select v-model="month" :disabled="year === null" @change="onMonthChange">
            <option :value="null">{{ t('settings.none') }}</option>
            <option v-for="m in months" :key="m" :value="m">{{ m }}</option>
          </select>
          <select v-model="day" :disabled="year === null || month === null">
            <option :value="null">{{ t('settings.none') }}</option>
            <option v-for="d in days" :key="d" :value="d">{{ d }}</option>
          </select>
        </div>
      </div>
      <div class="card-actions">
        <button v-if="basicDirty" class="btn ghost" :disabled="savingBasic" @click="revertBasic">
          {{ t('settings.undo') }}
        </button>
        <button class="btn primary" :disabled="savingBasic" @click="saveBasic">
          <span v-if="savingBasic" class="spinner"></span>
          {{ t('settings.saveBasic') }}
        </button>
      </div>
    </div>

    <!-- 管理游戏账户（主账号 + 小号 + 正版标签） -->
    <ManageAccounts :user="user" />

    <!-- 行式修改模块：头像 / 邮箱 / 密码 -->
    <div class="settings-card load-in" style="--load-delay: 160ms">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.avatar') }}</span>
        <button class="btn modify" @click="showAvatarDialog = true">
          <Pencil :size="16" />
          <span>{{ t('settings.modify') }}</span>
        </button>
      </div>
    </div>

    <div class="settings-card load-in" style="--load-delay: 240ms">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.email') }}</span>
        <button class="btn modify" @click="showEmailDialog = true">
          <Pencil :size="16" />
          <span>{{ t('settings.modify') }}</span>
        </button>
      </div>
    </div>

    <!-- 修改密码：验证码发送到本人邮箱且需旧密码，仅本人可用（管理员代管时不显示） -->
    <div v-if="user.is_self" class="settings-card load-in" style="--load-delay: 320ms">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.password') }}</span>
        <button class="btn modify" @click="showPasswordDialog = true">
          <Pencil :size="16" />
          <span>{{ t('settings.modify') }}</span>
        </button>
      </div>
    </div>

    <!-- 注销账号（危险操作，红色样式；仅本人，后端亦仅限本人） -->
    <div v-if="user.is_self" class="settings-card load-in" style="--load-delay: 400ms">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.cancelAccount') }}</span>
        <button class="btn modify danger" @click="showCancelDialog = true">
          <Trash2 :size="16" />
          <span>{{ t('settings.cancel') }}</span>
        </button>
      </div>
    </div>

    <!-- 头像对话框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showAvatarDialog" class="dialog-overlay" @click.self="showAvatarDialog = false">
        <div class="dialog">
          <h3 class="dialog-title">{{ t('settings.avatar') }}</h3>
          <!-- 大圆形可点击头像框：与 full_user_info.vue 一致 -->
          <label class="avatar-upload">
            <input type="file" accept="image/png,image/jpeg,image/webp,image/x-icon" @change="onAvatarChange" />
            <img
              v-if="avatarPreview || currentAvatar"
              :src="avatarPreview || currentAvatar"
              class="avatar-preview"
              alt="avatar"
            />
            <UserRound v-else :size="40" class="avatar-icon" />
            <span class="avatar-label">{{ t('settings.uploadAvatar') }}</span>
          </label>
          <div class="dialog-actions">
            <button class="btn cancel" @click="showAvatarDialog = false">{{ t('admin.cancel') }}</button>
            <button class="btn primary" :disabled="savingAvatar || !avatarFile" @click="uploadAvatar">
              <span v-if="savingAvatar" class="spinner"></span>
              {{ t('settings.uploadAvatar') }}
            </button>
          </div>
        </div>
      </div>
      </Transition>
    </Teleport>

    <!-- 邮箱对话框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showEmailDialog" class="dialog-overlay" @click.self="showEmailDialog = false">
        <div class="dialog">
          <h3 class="dialog-title">{{ t('settings.changeEmail') }}</h3>
          <div class="field">
            <label class="label">{{ t('settings.email') }}</label>
            <input v-model="newEmail" type="email" :placeholder="t('auth.email')" />
          </div>
          <div class="field">
            <label class="label">{{ t('auth.code') }}</label>
            <div class="code-row">
              <input v-model="emailCode" type="text" :placeholder="t('auth.code')" />
              <button class="btn ghost" :disabled="emailCooldown > 0 || emailSendingCode" @click="sendEmailCode">
                <span v-if="emailSendingCode" class="spinner"></span>
                {{ emailCooldown > 0 ? `${emailCooldown}s` : t('settings.sendCode') }}
              </button>
            </div>
          </div>
          <div class="h-captcha">
            <VueHcaptcha
              v-if="hcaptchaSiteKey"
              :sitekey="hcaptchaSiteKey"
              :theme="captchaTheme"
              api-endpoint="https://js.hcaptcha.com/1/api.js"
              @verify="onEmailCaptchaVerify"
              @expired="onEmailCaptchaExpired"
              @error="onEmailCaptchaError"
            />
          </div>
          <div class="dialog-actions">
            <button class="btn cancel" :disabled="savingEmail" @click="showEmailDialog = false">{{ t('admin.cancel') }}</button>
            <button class="btn primary" :disabled="savingEmail" @click="changeEmail">
              <span v-if="savingEmail" class="spinner"></span>
              {{ t('settings.changeEmail') }}
            </button>
          </div>
        </div>
      </div>
      </Transition>
    </Teleport>

    <!-- 密码对话框：change_password.vue 两页可复用组件 -->
    <ChangePassword
      v-if="showPasswordDialog"
      :uid="user.uid"
      @close="showPasswordDialog = false"
      @done="onPasswordDone"
    />

    <!-- 注销账号对话框 -->
    <CancelAccount v-if="showCancelDialog" :uid="user.uid" @close="showCancelDialog = false" />
  </section>
</template>

<style scoped>
.user-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-card {
  padding: 24px 28px;
  border-radius: 20px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

.card-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

/* 行式修改模块：左标题 / 右修改按钮 */
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.row-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
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

.field input,
.field select,
.profile-input {
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

.field select {
  background: var(--card-color);
  cursor: pointer;
}

.field select option {
  background: var(--card-color);
  color: var(--text-color);
}

.field select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.field input:focus,
.field select:focus,
.profile-input:focus {
  border-color: var(--text-color);
}

.profile-input {
  min-height: 180px;
  resize: vertical;
  line-height: 1.6;
}

.birthday-row {
  display: flex;
  gap: 10px;
}

.birthday-row select {
  flex: 1;
  min-width: 0;
}

.code-row {
  display: flex;
  gap: 10px;
}

.code-row input {
  flex: 1;
  min-width: 0;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

.h-captcha {
  margin-bottom: 16px;
}

.h-captcha :deep(iframe) {
  width: 100% !important;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.btn.ghost {
  flex-shrink: 0;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--links-color);
}

.btn.modify {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn.modify:hover {
  background: var(--btn-hover);
}

/* 危险操作（注销）按钮 */
.btn.modify.danger {
  border-color: rgba(229, 72, 77, 0.45);
  color: #e5484d;
}

.btn.modify.danger:hover {
  background: rgba(229, 72, 77, 0.1);
}

.btn.cancel {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 头像上传：大圆形可点击头像框（同 full_user_info.vue 风格），居中展示 */
.avatar-upload {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 120px;
  margin: 0 auto 20px;
  border-radius: 999px;
  overflow: hidden;
  border: 2px dashed rgba(148, 163, 184, 0.45);
  color: var(--links-color);
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.avatar-upload:hover {
  border-color: var(--text-color);
  background: var(--btn-hover);
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
  padding: 4px 0;
  font-size: 12px;
  text-align: center;
  color: #ffffff;
  background: rgba(0, 0, 0, 0.45);
}

/* 对话框 */
.dialog-overlay {
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

.dialog-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 700;
}

/* 按钮靠左：取消在前，主操作在后 */
.dialog-actions {
  display: flex;
  justify-content: flex-start;
  gap: 10px;
}
</style>

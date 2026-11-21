<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Pencil, UserRound, Trash2, LogOut } from 'lucide-vue-next'
import ChangePassword from './change_password.vue'
import CancelAccount from './cancel_account.vue'
import ManageAccounts from './manage_accounts.vue'
import MarkdownEditer from './markdown_editer.vue'
import HcaptchaBox from './hcaptcha_box.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { useDialogBox } from '../composables/useDialogBox'
import { useHcaptchaSiteKey } from '../composables/useHcaptchaSiteKey'
import { EMAIL_RE, useEmailCode } from '../composables/useEmailCode'

const props = defineProps({
  user: { type: Object, required: true },
  focusProfileKey: { type: Number, default: 0 },
})
const emit = defineEmits(['saved'])

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState, fetchMe, clearAuth } = useAuth()
const { showTip } = useTips()
const dialogBox = useDialogBox()
const hcaptchaSiteKey = useHcaptchaSiteKey()

// 退出登录：先弹全局确认框，确认后才清空本地登录态并回首页（与顶部用户菜单退出逻辑一致）
async function logout() {
  const ok = await dialogBox.confirm({
    title: t('settings.logoutConfirmTitle'),
    message: t('settings.logoutConfirmMessage'),
    danger: true,
  })
  if (!ok) return
  clearAuth()
  router.push('/')
}

// 基本资料（username / player_name 注册与加入时固定，不可修改）
const fullname = ref(props.user.fullname || '')
const gender = ref(props.user.gender ?? 'none') // 'none' | 'male' | 'female'
const birthYear = ref('')
const birthMonth = ref('')
const birthDay = ref('')
const yearInput = ref(null)
const monthInput = ref(null)
const dayInput = ref(null)

const genderOptions = computed(() => [
  { value: 'none', label: t('settings.none') },
  { value: 'male', label: t('settings.male') },
  { value: 'female', label: t('settings.female') },
])

// 简介
const profile = ref(props.user.profile || '')
const profileEditorRef = ref(null)

// 对话框开关（简介 / 基本资料 / 游戏账户 / 头像 / 邮箱 / 密码）
const showProfileDialog = ref(false)
const showBasicDialog = ref(false)
const showAccountsDialog = ref(false)
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
const savingEmail = ref(false)
const emailCaptchaToken = ref('')
const emailCaptchaRef = ref(null)

// 保存状态
const savingBasic = ref(false)
const savingProfile = ref(false)
const { sending: emailSendingCode, cooldown: emailCooldown, send: sendEmailCodeRequest } = useEmailCode()

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

// ---------- 生日输入（与注册表单 full_user_info.vue 一致） ----------

function pad2(n) {
  return n == null ? '' : String(n).padStart(2, '0')
}

function focusBirth(kind) {
  const map = { year: yearInput, month: monthInput, day: dayInput }
  const el = map[kind] && map[kind].value
  if (el) el.focus()
}

// 只保留数字；输入满 4/2/2 位后自动跳到下一个输入框
function onBirthInput(kind, event) {
  const max = kind === 'year' ? 4 : 2
  const el = event.target
  const digits = String(el.value || '').replace(/\D/g, '').slice(0, max)
  if (el.value !== digits) el.value = digits
  if (kind === 'year') birthYear.value = digits
  else if (kind === 'month') birthMonth.value = digits
  else birthDay.value = digits
  if (digits.length === max) {
    if (kind === 'year') focusBirth('month')
    else if (kind === 'month') focusBirth('day')
  }
}

// 非数字不键入；在空框按 Backspace 回到上一个框
function onBirthKeydown(kind, event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return
  if (event.key.length === 1 && !/[0-9]/.test(event.key)) {
    event.preventDefault()
    return
  }
  if (event.key === 'Backspace' && !event.target.value) {
    if (kind === 'month') {
      focusBirth('year')
      event.preventDefault()
    } else if (kind === 'day') {
      focusBirth('month')
      event.preventDefault()
    }
  }
}

// 粘贴：去掉非数字后按位数拆分（4=年，5/6=年月，7/8=年月日；7 位时给日补前导 0）
function onBirthPaste(kind, event) {
  event.preventDefault()
  const digits = String(event.clipboardData?.getData('text') || '').replace(/\D/g, '')
  if (!digits) return

  if (kind === 'year') {
    const year = digits.slice(0, 4)
    let rest = digits.slice(4)
    let month = ''
    let day = ''
    if (rest.length >= 2) {
      month = rest.slice(0, 2)
      rest = rest.slice(2)
    } else if (rest.length === 1) {
      month = `0${rest}`
      rest = ''
    }
    if (rest.length >= 1) day = rest.slice(0, 2).padStart(2, '0')
    birthYear.value = year
    birthMonth.value = month
    birthDay.value = day
    nextTick(() => {
      if (year.length < 4) focusBirth('year')
      else if (day) focusBirth('day')
      else if (month) focusBirth('day')
      else focusBirth('month')
    })
    return
  }

  if (kind === 'month') {
    birthMonth.value = digits.slice(0, 2)
    const rest = digits.slice(2)
    if (rest) birthDay.value = rest.slice(0, 2).padStart(2, '0')
    nextTick(() => focusBirth('day'))
    return
  }

  birthDay.value = digits.slice(0, 2)
}

// 级联：年空→整体不透露；年填月空→只存年；年月填日空→只存年月。
// 年/月/日都填时校验真实日期，且不能是未来日期。
function parseBirthday() {
  let year = birthYear.value ? Number(birthYear.value) : null
  let month = birthMonth.value ? Number(birthMonth.value) : null
  let day = birthDay.value ? Number(birthDay.value) : null

  if (year === null) {
    month = null
    day = null
  }
  if (month === null) day = null

  if (year !== null) {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    if (year < 1900 || year > today.getFullYear()) return { error: 'invalid' }
    if (month !== null && (month < 1 || month > 12)) return { error: 'invalid' }
    if (month !== null && day !== null) {
      const birthday = new Date(year, month - 1, day)
      if (
        birthday.getFullYear() !== year ||
        birthday.getMonth() !== month - 1 ||
        birthday.getDate() !== day
      ) {
        return { error: 'invalid' }
      }
      if (birthday.getTime() > today.getTime()) return { error: 'future' }
    }
  }
  return { birthday_year: year, birthday_month: month, birthday_day: day }
}

// 按服务器当前值重置基本资料表单（打开悬浮窗、撤销时使用）
function resetBasicFromUser() {
  fullname.value = props.user.fullname || ''
  gender.value = props.user.gender ?? 'none'
  birthYear.value = props.user.birthday_year ? String(props.user.birthday_year) : ''
  birthMonth.value = pad2(props.user.birthday_month)
  birthDay.value = pad2(props.user.birthday_day)
}

function openBasicDialog() {
  resetBasicFromUser()
  showBasicDialog.value = true
}

// 简介悬浮窗（"Edit Profile" 也走这里：打开弹窗并聚焦输入框）
function openProfileDialog() {
  profile.value = props.user.profile || ''
  showProfileDialog.value = true
  nextTick(() => profileEditorRef.value?.focus())
}

function openAccountsDialog() {
  showAccountsDialog.value = true
}

function focusProfile() {
  openProfileDialog()
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
  } else if (showProfileDialog.value) {
    showProfileDialog.value = false
  } else if (showBasicDialog.value) {
    showBasicDialog.value = false
  } else if (showAccountsDialog.value) {
    showAccountsDialog.value = false
  }
}

onMounted(() => {
  if (props.focusProfileKey > 0) focusProfile()
  document.addEventListener('keydown', handleKeydown)
})

// 撤销基本资料修改（恢复为服务器当前值）
function revertBasic() {
  resetBasicFromUser()
  showTip('info', t('settings.undone'))
}

// 撤销简介修改（恢复为服务器当前值）
function revertProfile() {
  profile.value = props.user.profile || ''
  showTip('info', t('settings.undone'))
}

// 是否有未保存的更改（决定撤销按钮是否渲染）
const profileDirty = computed(() => profile.value !== (props.user.profile || ''))

const basicDirty = computed(() => {
  const birthday = parseBirthday()
  if (birthday.error) return true
  return (
    fullname.value !== (props.user.fullname || '') ||
    (gender.value === 'none' ? null : gender.value) !== (props.user.gender ?? null) ||
    birthday.birthday_year !== (props.user.birthday_year ?? null) ||
    birthday.birthday_month !== (props.user.birthday_month ?? null) ||
    birthday.birthday_day !== (props.user.birthday_day ?? null)
  )
})

// 保存基本资料
async function saveBasic() {
  const birthday = parseBirthday()
  if (birthday.error === 'invalid') {
    showTip('warning', t('register.birthday_invalid'))
    return
  }
  if (birthday.error === 'future') {
    showTip('warning', t('register.birthday_future'))
    return
  }
  savingBasic.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/info`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        fullname: fullname.value.trim(),
        gender: gender.value === 'none' ? null : gender.value,
        birthday_year: birthday.birthday_year,
        birthday_month: birthday.birthday_month,
        birthday_day: birthday.birthday_day,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.basicSaved'))
      showBasicDialog.value = false
      fetchMe() // 基本资料变更：刷新公共用户数据
      emit('saved')
      resetBasicFromUser()
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
      showProfileDialog.value = false
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
  await sendEmailCodeRequest(newEmail.value, {
    hcaptchaToken: emailCaptchaToken.value,
    resetCaptcha: () => {
      emailCaptchaToken.value = ''
      emailCaptchaRef.value?.reset()
    },
  })
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
})
</script>

<template>
  <section class="user-settings">
    <!-- 个人简介：一行式入口 + 悬浮窗编辑 -->
    <div class="settings-card load-in">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.profile') }}</span>
        <button class="btn modify" @click="openProfileDialog">
          <Pencil :size="16" />
          <span>{{ t('settings.modify') }}</span>
        </button>
      </div>
    </div>

    <!-- 基本资料（username / player_name 固定不可改）：悬浮窗编辑，性别 / 生日与注册表单一致 -->
    <div class="settings-card load-in" style="--load-delay: 80ms">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.basic') }}</span>
        <button class="btn modify" @click="openBasicDialog">
          <Pencil :size="16" />
          <span>{{ t('settings.modify') }}</span>
        </button>
      </div>
    </div>

    <!-- 管理游戏账户（主账号 + 小号 + 正版标签）：悬浮窗编辑 -->
    <div class="settings-card load-in" style="--load-delay: 120ms">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.manageAccounts') }}</span>
        <button class="btn modify" @click="openAccountsDialog">
          <Pencil :size="16" />
          <span>{{ t('settings.modify') }}</span>
        </button>
      </div>
    </div>

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

    <!-- 退出登录（仅本人；位于注销账号之上） -->
    <div v-if="user.is_self" class="settings-card load-in" style="--load-delay: 360ms">
      <div class="setting-row">
        <span class="row-title">{{ t('settings.session') }}</span>
        <button class="btn modify" @click="logout">
          <LogOut :size="16" />
          <span>{{ t('userMenu.sign_out') }}</span>
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

    <!-- 个人简介悬浮窗 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showProfileDialog" class="dialog-overlay">
          <div class="dialog dialog-editor">
            <h3 class="dialog-title">{{ t('settings.profile') }}</h3>
            <MarkdownEditer
              ref="profileEditorRef"
              v-model="profile"
              :placeholder="t('settings.profilePlaceholder')"
              :min-height="180"
            />
            <div class="dialog-actions">
              <button class="btn cancel" :disabled="savingProfile" @click="showProfileDialog = false">
                {{ t('admin.cancel') }}
              </button>
              <button v-if="profileDirty" class="btn cancel" :disabled="savingProfile" @click="revertProfile">
                {{ t('settings.undo') }}
              </button>
              <button class="btn primary" :disabled="savingProfile" @click="saveProfile">
                <span v-if="savingProfile" class="spinner"></span>
                {{ t('settings.saveProfile') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 基本资料悬浮窗（性别 / 生日与注册表单一致） -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showBasicDialog" class="dialog-overlay">
          <div class="dialog">
            <h3 class="dialog-title">{{ t('settings.basic') }}</h3>
            <div class="field">
              <label class="label">{{ t('settings.fullname') }}</label>
              <input v-model="fullname" type="text" :placeholder="t('settings.fullname')" />
            </div>
            <div class="field">
              <span class="label">{{ t('settings.gender') }}</span>
              <div class="radio-row" role="radiogroup" :aria-label="t('settings.gender')">
                <label
                  v-for="opt in genderOptions"
                  :key="opt.value"
                  class="radio-item"
                  :class="{ active: gender === opt.value }"
                >
                  <input v-model="gender" type="radio" name="settings-gender" :value="opt.value" />
                  <span class="radio-dot" aria-hidden="true"></span>
                  <span>{{ opt.label }}</span>
                </label>
              </div>
            </div>
            <div class="field">
              <span class="label">{{ t('settings.birthday') }}</span>
              <div class="birthday-row">
                <input
                  ref="yearInput"
                  :value="birthYear"
                  class="birth-input"
                  type="text"
                  inputmode="numeric"
                  maxlength="4"
                  placeholder="YYYY"
                  aria-label="YYYY"
                  @input="onBirthInput('year', $event)"
                  @keydown="onBirthKeydown('year', $event)"
                  @paste="onBirthPaste('year', $event)"
                />
                <span class="birth-sep" aria-hidden="true">/</span>
                <input
                  ref="monthInput"
                  :value="birthMonth"
                  class="birth-input"
                  type="text"
                  inputmode="numeric"
                  maxlength="2"
                  placeholder="MM"
                  aria-label="MM"
                  @input="onBirthInput('month', $event)"
                  @keydown="onBirthKeydown('month', $event)"
                  @paste="onBirthPaste('month', $event)"
                />
                <span class="birth-sep" aria-hidden="true">/</span>
                <input
                  ref="dayInput"
                  :value="birthDay"
                  class="birth-input"
                  type="text"
                  inputmode="numeric"
                  maxlength="2"
                  placeholder="DD"
                  aria-label="DD"
                  @input="onBirthInput('day', $event)"
                  @keydown="onBirthKeydown('day', $event)"
                  @paste="onBirthPaste('day', $event)"
                />
              </div>
              <p class="birth-hint">{{ t('register.birthday_hint') }}</p>
            </div>
            <div class="dialog-actions">
              <button class="btn cancel" :disabled="savingBasic" @click="showBasicDialog = false">
                {{ t('admin.cancel') }}
              </button>
              <button v-if="basicDirty" class="btn cancel" :disabled="savingBasic" @click="revertBasic">
                {{ t('settings.undo') }}
              </button>
              <button class="btn primary" :disabled="savingBasic" @click="saveBasic">
                <span v-if="savingBasic" class="spinner"></span>
                {{ t('settings.saveBasic') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 管理游戏账户悬浮窗 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showAccountsDialog" class="dialog-overlay">
          <div class="dialog dialog-wide">
            <h3 class="dialog-title">{{ t('settings.manageAccounts') }}</h3>
            <ManageAccounts :user="user" frameless />
            <div class="dialog-actions">
              <button class="btn cancel" @click="showAccountsDialog = false">{{ t('admin.cancel') }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 头像对话框 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showAvatarDialog" class="dialog-overlay">
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
        <div v-if="showEmailDialog" class="dialog-overlay">
        <div class="dialog">
          <h3 class="dialog-title">{{ t('settings.changeEmail') }}</h3>
          <div class="field">
            <label class="float-field">
              <input v-model="newEmail" type="email" placeholder=" " />
              <span class="float-label">{{ t('settings.email') }}</span>
            </label>
          </div>
          <div class="field">
            <div class="code-row">
              <label class="float-field">
                <input v-model="emailCode" type="text" placeholder=" " />
                <span class="float-label">{{ t('auth.code') }}</span>
              </label>
              <button class="btn ghost" :disabled="emailCooldown > 0 || emailSendingCode" @click="sendEmailCode">
                <span v-if="emailSendingCode" class="spinner"></span>
                {{ emailCooldown > 0 ? `${emailCooldown}s` : t('settings.sendCode') }}
              </button>
            </div>
          </div>
          <div class="h-captcha">
            <HcaptchaBox
              v-if="hcaptchaSiteKey"
              ref="emailCaptchaRef"
              :sitekey="hcaptchaSiteKey"
              :theme="captchaTheme"
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

/* 性别单选（与注册表单 full_user_info.vue 一致） */
.radio-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.radio-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: var(--card-color);
  color: var(--text-color);
  cursor: pointer;
  font: inherit;
  transition: border-color 0.2s ease;
}

.radio-item input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.radio-item:focus-within {
  border-color: var(--text-color);
}

.radio-dot {
  flex-shrink: 0;
  position: relative;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid currentColor;
  opacity: 0.6;
}

.radio-item.active .radio-dot {
  border-color: var(--links-color);
  opacity: 1;
}

.radio-item.active .radio-dot::after {
  content: '';
  position: absolute;
  inset: 2px;
  border-radius: 50%;
  background: var(--links-color);
}

.radio-item.active {
  border-color: var(--links-color);
}

/* 生日输入（与注册表单 full_user_info.vue 一致） */
.birthday-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.birth-input {
  flex: 1;
  min-width: 0;
  text-align: center;
}

.birth-sep {
  flex-shrink: 0;
  color: var(--links-color);
}

.birth-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--links-color);
}

.code-row {
  display: flex;
  gap: 10px;
}

.h-captcha {
  margin-bottom: 16px;
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
  background: var(--float-bg);
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
  background: var(--float-bg);
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

.dialog-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 700;
}

/* 管理游戏账户悬浮窗：内容比普通表单宽 */
.dialog-wide {
  width: min(520px, 100%);
}

/* Markdown 编辑器弹窗：宽度足够放下标签 + 语法工具条，避免工具条换行导致高度跳动 */
.dialog-editor {
  width: min(760px, 100%);
}

/* 按钮靠左：取消在前，主操作在后 */
.dialog-actions {
  display: flex;
  justify-content: flex-start;
  gap: 10px;
}
</style>

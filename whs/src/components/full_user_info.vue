<script setup>
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { User } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const props = defineProps({
  uid: { type: [Number, String], required: true },
})
const emit = defineEmits(['done'])

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState, fetchMe } = useAuth()
const { showTip } = useTips()

const gender = ref('none') // 'none' | 'male' | 'female'
const genderOptions = computed(() => [
  { value: 'none', label: t('register.none') },
  { value: 'male', label: t('register.gender_male') },
  { value: 'female', label: t('register.gender_female') },
])

// 生日：三个输入框（YYYY / MM / DD），留空即“不透露”，支持粘贴自动拆分
const birthYear = ref('')
const birthMonth = ref('')
const birthDay = ref('')
const yearInput = ref(null)
const monthInput = ref(null)
const dayInput = ref(null)

const avatarFile = ref(null)
const avatarPreview = ref('')
const loading = ref(false)

function focusBirth(kind) {
  const map = { year: yearInput, month: monthInput, day: dayInput }
  const el = map[kind] && map[kind].value
  if (el) el.focus()
}

function onFileChange(event) {
  const f = event.target.files && event.target.files[0]
  if (!f) return
  avatarFile.value = f
  avatarPreview.value = URL.createObjectURL(f)
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

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function submit() {
  loading.value = true
  try {
    const birthday = parseBirthday()
    if (birthday.error === 'invalid') {
      showTip('warning', t('register.birthday_invalid'))
      return
    }
    if (birthday.error === 'future') {
      showTip('warning', t('register.birthday_future'))
      return
    }

    if (avatarFile.value) {
      const fd = new FormData()
      fd.append('file', avatarFile.value)
      const avRes = await fetch(`/api/user/${props.uid}/avatar`, {
        method: 'POST',
        headers: authState.token ? { Authorization: `Bearer ${authState.token}` } : {},
        body: fd,
      })
      if (!avRes.ok) {
        showTip('error', t('auth.request_failed'))
        return
      }
    }

    const res = await fetch(`/api/user/${props.uid}/info`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
      },
      body: JSON.stringify({
        gender: gender.value === 'none' ? null : gender.value,
        birthday_year: birthday.birthday_year,
        birthday_month: birthday.birthday_month,
        birthday_day: birthday.birthday_day,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showTip('error', localMessage(data))
      return
    }
    fetchMe() // 注册资料完善：刷新公共用户数据（头像/性别/生日已更新）
    emit('done')
    router.push('/joinus')
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="full-user-info">
    <h1 class="title">{{ t('register.finish') }}</h1>

    <!-- 顶部：上传头像 -->
    <label class="avatar-upload">
      <input type="file" accept="image/png,image/jpeg,image/webp,image/x-icon" @change="onFileChange" />
      <img v-if="avatarPreview" :src="avatarPreview" class="avatar-preview" alt="avatar" />
      <User v-else :size="30" class="avatar-icon" />
      <span class="avatar-label">{{ t('auth.upload_avatar') }}</span>
    </label>

    <!-- 性别：单选 -->
    <div class="field">
      <span class="label">{{ t('register.gender') }}</span>
      <div class="radio-row" role="radiogroup" :aria-label="t('register.gender')">
        <label
          v-for="opt in genderOptions"
          :key="opt.value"
          class="radio-item"
          :class="{ active: gender === opt.value }"
        >
          <input v-model="gender" type="radio" name="gender" :value="opt.value" />
          <span class="radio-dot" aria-hidden="true"></span>
          <span>{{ opt.label }}</span>
        </label>
      </div>
    </div>

    <!-- 生日：YYYY / MM / DD 三个输入框，留空即不透露 -->
    <div class="field">
      <span class="label">{{ t('register.birthday') }}</span>
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

    <button type="button" class="finish" :disabled="loading" @click="submit">
      <span v-if="loading" class="spinner"></span>
      {{ t('register.finish') }}
    </button>
  </div>
</template>

<style scoped>
.title {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-color);
  text-align: center;
}

.avatar-upload {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  margin: 0 auto 20px;
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
  background: var(--card-color);
  color: var(--text-color);
  font: inherit;
  outline: none;
  transition: border-color 0.2s ease;
}

.field input:focus {
  border-color: var(--text-color);
}

/* 性别单选 */
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

/* 生日输入 */
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

.finish {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
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

.finish:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

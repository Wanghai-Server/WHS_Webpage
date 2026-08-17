<script setup>
import { ref, computed } from 'vue'
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
const { state: authState } = useAuth()
const { showTip } = useTips()

const gender = ref(null) // 'male' | 'female' | null
const year = ref(null)   // int | null
const month = ref(null)
const day = ref(null)

const avatarFile = ref(null)
const avatarPreview = ref('')
const loading = ref(false)

const currentYear = new Date().getFullYear()
const years = computed(() => {
  const arr = []
  for (let y = currentYear; y >= 1920; y--) arr.push(y)
  return arr
})
const months = Array.from({ length: 12 }, (_, i) => i + 1)
const days = Array.from({ length: 31 }, (_, i) => i + 1)

function onFileChange(event) {
  const f = event.target.files && event.target.files[0]
  if (!f) return
  avatarFile.value = f
  avatarPreview.value = URL.createObjectURL(f)
}

// 级联：年=不透露 → 月、日强制不透露；月=不透露 → 日强制不透露
function onYearChange() {
  if (year.value === null) {
    month.value = null
    day.value = null
  } else if (month.value === null) {
    day.value = null
  }
}

function onMonthChange() {
  if (month.value === null) {
    day.value = null
  }
}

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function submit() {
  loading.value = true
  try {
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
        gender: gender.value,
        birthday_year: year.value,
        birthday_month: month.value,
        birthday_day: day.value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showTip('error', localMessage(data))
      return
    }
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

    <!-- 性别 -->
    <div class="field">
      <label class="label">{{ t('register.gender') }}</label>
      <select v-model="gender">
        <option :value="null">{{ t('register.none') }}</option>
        <option value="male">{{ t('register.gender_male') }}</option>
        <option value="female">{{ t('register.gender_female') }}</option>
      </select>
    </div>

    <!-- 生日：年 / 月 / 日 -->
    <div class="field">
      <label class="label">{{ t('register.birthday') }}</label>
      <div class="birthday-row">
        <select v-model="year" @change="onYearChange">
          <option :value="null">{{ t('register.none') }}</option>
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
        <select v-model="month" :disabled="year === null" @change="onMonthChange">
          <option :value="null">{{ t('register.none') }}</option>
          <option v-for="m in months" :key="m" :value="m">{{ m }}</option>
        </select>
        <select v-model="day" :disabled="year === null || month === null">
          <option :value="null">{{ t('register.none') }}</option>
          <option v-for="d in days" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
    </div>

    <button type="button" class="finish" :disabled="loading" @click="submit">
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

.field input,
.field select {
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

.field select option {
  background: var(--card-color);
  color: var(--text-color);
}

.field input:focus,
.field select:focus {
  border-color: var(--text-color);
}

.field select {
  cursor: pointer;
}

.field select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.birthday-row {
  display: flex;
  gap: 10px;
}

.birthday-row select {
  flex: 1;
  min-width: 0;
}

.finish {
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

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { User, Settings, LogOut } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'

const { t } = useI18n()
const router = useRouter()
const { state, clearAuth } = useAuth()

const user = computed(() => state.user)

const avatarSrc = computed(() =>
  user.value && user.value.avatar ? `/api/user/${user.value.uid}/avatar` : ''
)

const username = computed(() => user.value?.username || 'User')
const fullname = computed(() => user.value?.fullname || '')

// 个人资料：用户页 profile 标签（?tab=profile）
function goProfile() {
  router.push({ path: `/user/${user.value?.uid}`, query: { tab: 'profile' } })
}

// 设置：用户页 settings 标签（?tab=settings），由页面按 URL query 自动映射
function goSettings() {
  router.push({ path: `/user/${user.value?.uid}`, query: { tab: 'settings' } })
}

function signOut() {
  clearAuth()
  router.push('/')
}
</script>

<template>
  <div class="user-dropdown">
    <!-- 第一行：头像 + 用户名（左），红色 Sign out 图标（右） -->
    <div class="dropdown-head">
      <div class="dropdown-user">
        <img v-if="avatarSrc" :src="avatarSrc" class="dropdown-avatar" alt="avatar" />
        <span v-else class="dropdown-avatar dropdown-avatar-fallback"><User :size="18" /></span>
        <div class="dropdown-names" :class="{ single: !fullname }">
          <span class="dropdown-username">{{ username }}</span>
          <span v-if="fullname" class="dropdown-fullname">{{ fullname }}</span>
        </div>
      </div>
      <button
        class="dropdown-signout"
        type="button"
        :title="t('userMenu.sign_out')"
        :aria-label="t('userMenu.sign_out')"
        @click="signOut"
      >
        <LogOut :size="18" />
      </button>
    </div>

    <!-- 第二行：Profile -->
    <button class="dropdown-item" type="button" @click="goProfile">
      <User :size="18" />
      <span>{{ t('userMenu.profile') }}</span>
    </button>

    <!-- 第三行：Settings -->
    <button class="dropdown-item" type="button" @click="goSettings">
      <Settings :size="18" />
      <span>{{ t('userMenu.settings') }}</span>
    </button>
  </div>
</template>

<style scoped>
.user-dropdown {
  min-width: 200px;
  padding: 8px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 2px;

  /* 背景、透明度、毛玻璃均参考导航栏（.navbar.scrolled） */
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  color: var(--text-color);
}

/* 第一行 */
.dropdown-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  margin-bottom: 4px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.dropdown-user {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.dropdown-avatar {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  object-fit: cover;
  flex-shrink: 0;
}

.dropdown-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--btn-hover);
  color: var(--links-color);
}

.dropdown-names {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  line-height: 1.25;
}

.dropdown-username {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 只有 username 时：字号更大、与头像适配 */
.dropdown-names.single .dropdown-username {
  font-size: 18px;
}

.dropdown-fullname {
  font-size: 13px;
  color: var(--links-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 红色 Sign out 图标 */
.dropdown-signout {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #e5484d;
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color 0.15s ease;
}

.dropdown-signout:hover {
  background: var(--btn-hover);
}

/* 第二 / 三行按钮 */
.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s ease;
}

.dropdown-item:hover {
  background: var(--btn-hover);
}

.dropdown-item svg {
  flex-shrink: 0;
  color: var(--links-color);
}
</style>

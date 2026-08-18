<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import BasicUserInfo from '../components/basic_user_info.vue'
import UserProfile from '../components/user_profile.vue'
import UserSettings from '../components/user_settings.vue'
import AdminSettings from '../components/admin_settings.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

const user = ref(null)
const loading = ref(true)
const activeTab = ref('profile')
const focusProfileKey = ref(0)

const uid = computed(() => Number(route.params.uid))

const isSelf = computed(() => !!user.value?.is_self)
const isAdmin = computed(() => (user.value?.permission ?? 0) >= 3)
// 当前登录用户是否为管理员（管理员可代管他人设置页）
const viewerIsAdmin = computed(() => (authState.user?.permission ?? 0) >= 3)

// 标签：profile 恒有；settings 仅本人或管理员代管；admin settings 仅本人且为管理员
const tabs = computed(() => {
  const list = [{ key: 'profile', label: t('user.tabProfile') }]
  if (isSelf.value || viewerIsAdmin.value) {
    list.push({ key: 'settings', label: t('user.tabSettings') })
  }
  if (isSelf.value && isAdmin.value) {
    list.push({ key: 'admin', label: t('user.tabAdmin') })
  }
  return list
})

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function fetchUser() {
  loading.value = true
  try {
    const res = await fetch(`/api/user/${uid.value}`, {
      headers: authState.token ? { Authorization: `Bearer ${authState.token}` } : {},
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      user.value = data
      // 根据 URL query 校正标签（?tab=profile|settings|admin）
      applyTabFromQuery()
    } else {
      showTip('error', localMessage(data))
      user.value = null
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
    user.value = null
  } finally {
    loading.value = false
  }
}

// 标签合法性：settings 仅本人或管理员代管；admin 仅本人且为管理员；否则回退 profile
function resolveTab(tab) {
  const t = String(tab || 'profile')
  if (t === 'settings') return isSelf.value || viewerIsAdmin.value ? 'settings' : 'profile'
  if (t === 'admin') {
    if (!isSelf.value) return 'profile'
    return isAdmin.value ? 'admin' : 'settings'
  }
  return 'profile'
}

// 用 URL query 里的 ?tab= 校正当前标签
function applyTabFromQuery() {
  if (!user.value) return
  activeTab.value = resolveTab(route.query.tab)
}

// 切换标签并同步到 URL query（浏览器前进/后退/刷新保持一致）
function setTab(tab) {
  activeTab.value = tab
  router.replace({ query: { ...route.query, tab } })
}

// 本人点击 "Edit Profile"：切到设置页并聚焦简介编辑
function onEditProfile() {
  setTab('settings')
  focusProfileKey.value += 1
}

// 关注状态变更：同步到本地数据
function onFollowChanged(patch) {
  if (!user.value) return
  user.value.is_following = patch.is_following
  user.value.followers_count = patch.followers_count
  user.value.followings_count = patch.followings_count
}

watch(uid, fetchUser, { immediate: true })

// 同一页面内 URL query 变化（如下拉菜单跳转 ?tab=settings）时切换标签；
// 切换用户期间 loading 为 true 时跳过，由 fetchUser 完成后的 applyTabFromQuery 兜底
watch(
  () => route.query.tab,
  (tab) => {
    if (!user.value || loading.value) return
    activeTab.value = resolveTab(tab)
  }
)
</script>

<template>
  <Top_navbar />

  <main class="user-page">
    <div v-if="loading" class="placeholder">{{ t('admin.loading') }}</div>

    <template v-else-if="user">
      <div class="load-in">
        <BasicUserInfo :user="user" @edit-profile="onEditProfile" @follow-changed="onFollowChanged" />
      </div>

      <div class="tab-bar load-in" style="--load-delay: 80ms">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab"
          :class="{ active: activeTab === tab.key }"
          @click="setTab(tab.key)"
        >{{ tab.label }}</button>
      </div>

      <div class="tab-content">
        <UserProfile v-if="activeTab === 'profile'" :user="user" />
        <UserSettings
          v-else-if="activeTab === 'settings'"
          :user="user"
          :focus-profile-key="focusProfileKey"
          @saved="fetchUser"
        />
        <AdminSettings v-else-if="activeTab === 'admin'" :self-uid="user.uid" />
      </div>
    </template>

    <div v-else class="placeholder">
      <p>{{ t('user.loadFailed') }}</p>
    </div>
  </main>

  <Page_footer />
</template>

<style scoped>
.user-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 100px 24px 40px;
  box-sizing: border-box;
  min-height: 60vh;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.placeholder {
  padding: 120px 0;
  text-align: center;
  color: var(--links-color);
}

.tab-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tab {
  padding: 10px 22px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab:hover {
  color: var(--text-color);
}

.tab.active {
  background: var(--text-color);
  color: var(--bg-color);
  border-color: transparent;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>

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
import AdminUserPanel from '../components/admin_user_panel.vue'
import FollowList from '../components/follow_list.vue'
import Tabs from '../components/tabs.vue'
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

// 粉丝/关注悬浮窗
const followListOpen = ref(false)
const followListTab = ref('followers')
function openFollowList(tab) {
  followListTab.value = tab
  followListOpen.value = true
}

const uid = computed(() => Number(route.params.uid))

const isSelf = computed(() => !!user.value?.is_self)
const isAdmin = computed(() => (user.value?.permission ?? 0) >= 3)
// 当前登录用户是否为管理员（管理员可代管他人设置页）
const viewerIsAdmin = computed(() => (authState.user?.permission ?? 0) >= 3)

// 标签：profile 恒有；settings 仅本人或管理员代管；
// admin 在两种情况出现：本人且为管理员（完整后台），或管理员查看他人页面（仅三个操作按钮）
const tabs = computed(() => {
  const list = [{ key: 'profile', label: t('user.tabProfile') }]
  if (isSelf.value || viewerIsAdmin.value) {
    list.push({ key: 'settings', label: t('user.tabSettings') })
  }
  if ((isSelf.value && isAdmin.value) || viewerIsAdmin.value) {
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

// 标签合法性：settings 仅本人或管理员代管；
// admin 在"本人且为管理员"或"管理员查看他人页面"时合法；否则回退 profile
function resolveTab(tab) {
  const t = String(tab || 'profile')
  if (t === 'settings') return isSelf.value || viewerIsAdmin.value ? 'settings' : 'profile'
  if (t === 'admin') {
    return (isSelf.value && isAdmin.value) || viewerIsAdmin.value ? 'admin' : 'profile'
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
    <div v-if="loading" class="placeholder"><span class="spinner"></span>{{ t('admin.loading') }}</div>

    <template v-else-if="user">
      <div class="load-in">
        <BasicUserInfo
          :user="user"
          @edit-profile="onEditProfile"
          @follow-changed="onFollowChanged"
          @open-follow-list="openFollowList"
        />
      </div>

      <div class="tab-bar load-in" style="--load-delay: 80ms">
        <Tabs :model-value="activeTab" :items="tabs" @update:model-value="setTab" />
      </div>

      <div class="tab-content">
        <UserProfile v-if="activeTab === 'profile'" :user="user" />
        <UserSettings
          v-else-if="activeTab === 'settings'"
          :user="user"
          :focus-profile-key="focusProfileKey"
          @saved="fetchUser"
        />
        <!-- 管理员本人页面：完整后台（用户管理 / 考试管理 / 试卷管理） -->
        <AdminSettings v-else-if="activeTab === 'admin' && isSelf" :self-uid="user.uid" />
        <!-- 管理员查看他人页面：仅三个操作（封禁/解禁、查看答题卡、解锁） -->
        <AdminUserPanel v-else-if="activeTab === 'admin'" :user="user" @changed="fetchUser" />
      </div>
    </template>

    <div v-else class="placeholder">
      <p>{{ t('user.loadFailed') }}</p>
    </div>
  </main>

  <!-- 粉丝/关注悬浮窗（可复用组件） -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <FollowList
        v-if="followListOpen && user"
        :uid="user.uid"
        :initial-tab="followListTab"
        @close="followListOpen = false"
      />
    </Transition>
  </Teleport>

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
  flex-wrap: wrap;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Eye, UserRound, X } from 'lucide-vue-next'
import Tabs from './tabs.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

// 可复用的粉丝/关注悬浮窗：
// 展示某用户的全部粉丝与关注，用 tabs 导航分开（同一组件内），
// 每个用户右侧带一个 "see" 按钮（与管理员页面同款），点击跳转其主页。
const props = defineProps({
  uid: { type: Number, required: true },
  initialTab: { type: String, default: 'followers' }, // 'followers' | 'followings'
})

const emit = defineEmits(['close'])

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()

const activeTab = ref(props.initialTab === 'followings' ? 'followings' : 'followers')
const tabItems = [
  { key: 'followers', label: t('user.followers') },
  { key: 'followings', label: t('user.followings') },
]

// 各 tab 的列表数据
const users = ref([])
const loading = ref(false)

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

async function fetchList() {
  loading.value = true
  users.value = []
  try {
    const res = await fetch(`/api/user/${props.uid}/${activeTab.value}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      users.value = data.users || []
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}

function onTabChange(tab) {
  if (tab !== activeTab.value) {
    activeTab.value = tab
    fetchList()
  }
}

// "see" 按钮：与管理员页面同款，跳转目标用户主页
function seeUser(u) {
  router.push(`/user/${u.uid}`)
}

function avatarSrc(u) {
  return u.avatar ? `/api/user/${u.uid}/avatar` : ''
}

function displayName(u) {
  return u.fullname || u.username || ''
}

function handleKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

watch(
  () => props.uid,
  () => fetchList()
)

onMounted(() => {
  fetchList()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="fl-overlay" @click.self="emit('close')">
    <div class="fl-modal dialog">
      <header class="fl-head">
        <h3>{{ activeTab === 'followers' ? t('user.followers') : t('user.followings') }}</h3>
        <button type="button" class="fl-close" :aria-label="t('message.close')" @click="emit('close')">
          <X :size="18" />
        </button>
      </header>

      <div class="fl-tabs">
        <Tabs :model-value="activeTab" :items="tabItems" @update:model-value="onTabChange" />
      </div>

      <div class="fl-body">
        <div v-if="loading" class="fl-empty"><span class="spinner"></span>{{ t('admin.loading') }}</div>
        <p v-else-if="users.length === 0" class="fl-empty">
          {{ activeTab === 'followers' ? t('user.followersEmpty') : t('user.followingsEmpty') }}
        </p>
        <ul v-else class="fl-list">
          <li v-for="u in users" :key="u.uid" class="fl-row">
            <img v-if="avatarSrc(u)" :src="avatarSrc(u)" class="fl-avatar" alt="avatar" loading="lazy" />
            <span v-else class="fl-avatar fl-avatar-fallback"><UserRound :size="20" /></span>
            <div class="fl-info">
              <span class="fl-name">{{ displayName(u) }}</span>
              <span class="fl-username">{{ u.username }}</span>
            </div>
            <button
              type="button"
              class="fl-see"
              :title="t('admin.view')"
              :aria-label="t('admin.view')"
              @click="seeUser(u)"
            >
              <Eye :size="18" />
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fl-overlay {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

/* .dialog 类复用 style.css 的 dialog-fade 弹出动画；面板为半透明毛玻璃 */
.fl-modal {
  width: min(440px, 100%);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.3);
}

.fl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px 0;
}

.fl-head h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-color);
}

.fl-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
}

.fl-close:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.fl-tabs {
  padding: 12px 20px 0;
}

.fl-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 20px 20px;
}

.fl-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--links-color);
}

.fl-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fl-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 12px;
  transition: background-color 0.15s ease;
}

.fl-row:hover {
  background: var(--btn-hover);
}

.fl-avatar {
  width: 40px;
  height: 40px;
  border-radius: 999px;
  object-fit: cover;
  flex-shrink: 0;
}

.fl-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--btn-hover);
  color: var(--links-color);
}

.fl-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.fl-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fl-username {
  font-size: 12.5px;
  color: var(--links-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* "see" 按钮：与管理员页面 icon-btn 同款 */
.fl-see {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  flex-shrink: 0;
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.fl-see:hover {
  color: #ebaa28;
  border-color: rgba(235, 170, 40, 0.5);
  background: rgba(235, 170, 40, 0.08);
}
</style>

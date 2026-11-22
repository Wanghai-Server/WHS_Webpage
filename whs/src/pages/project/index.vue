<script setup>
/**
 * 工程管理页（/projects）。
 *
 * - 公开浏览：按状态筛选、查看详情；
 * - 发起 / 认领 / 完成 / 删除 / 编辑描述与备注的权限由后端 viewer 标记决定；
 * - 游戏服务器离线时显示横幅并禁用写操作（列表使用后端缓存）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { FolderKanban, Plus } from 'lucide-vue-next'
import Top_navbar from '../../components/top_navbar.vue'
import Page_footer from '../../components/page_footer.vue'
import ProjectCreate from '../../components/project_create.vue'
import ProjectDetail from '../../components/project_detail.vue'
import { useAuth } from '../../composables/useAuth'
import { useTips } from '../../composables/useTips'

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()

const EMPTY_COUNTS = { all: 0, unclaimed: 0, claimed: 0, completed: 0 }

const items = ref([])
const counts = ref({ ...EMPTY_COUNTS })
const online = ref(true)
const loading = ref(false)
const activeStatus = ref('all')

const createOpen = ref(false)
const detailOpen = ref(false)
const detailProject = ref(null)
const detailViewer = ref({})

const accounts = ref([])
const defaultAccount = ref('')

const isLoggedIn = computed(() => !!authState.token)
const permission = computed(() => authState.user?.permission ?? 0)
const canCreate = computed(() => isLoggedIn.value && permission.value >= 3)

const statusTabs = computed(() => [
  { value: 'all', label: t('projects.filterAll'), count: counts.value.all },
  { value: 'unclaimed', label: t('projects.statusUnclaimed'), count: counts.value.unclaimed },
  { value: 'claimed', label: t('projects.statusClaimed'), count: counts.value.claimed },
  { value: 'completed', label: t('projects.statusCompleted'), count: counts.value.completed },
])

const filteredItems = computed(() =>
  activeStatus.value === 'all'
    ? items.value
    : items.value.filter((item) => item.status === activeStatus.value)
)

function authHeaders(extra = {}) {
  return {
    ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
    ...extra,
  }
}

function localMessage(data) {
  const message = data && data.message
  if (!message) return t('auth.request_failed')
  return message[locale.value] || message.zh || message.en || ''
}

function statusKey(status) {
  return `projects.status${status.charAt(0).toUpperCase()}${status.slice(1)}`
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function fetchProjects() {
  loading.value = true
  try {
    const res = await fetch('/api/projects', { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      items.value = Array.isArray(data.items) ? data.items : []
      counts.value = { ...EMPTY_COUNTS, ...(data.counts || {}) }
      online.value = data.online !== false
    } else {
      items.value = []
      counts.value = { ...EMPTY_COUNTS }
      online.value = false
      console.warn('[projects] 列表加载失败', data)
    }
  } catch (e) {
    items.value = []
    counts.value = { ...EMPTY_COUNTS }
    online.value = false
    console.warn(e)
  } finally {
    loading.value = false
  }
}

async function fetchAccounts() {
  if (!authState.token) {
    accounts.value = []
    defaultAccount.value = ''
    return
  }
  try {
    const res = await fetch('/api/projects/accounts', { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      accounts.value = Array.isArray(data.accounts) ? data.accounts : []
      defaultAccount.value = data.default || ''
    }
  } catch (e) {
    console.warn(e)
  }
}

function openCreate() {
  if (!online.value) {
    showTip('warning', t('projects.serverOfflineHint'))
    return
  }
  if (!isLoggedIn.value) {
    showTip('warning', t('projects.loginRequired'))
    router.push('/login')
    return
  }
  if (!canCreate.value) {
    showTip('warning', t('projects.needAdmin'))
    return
  }
  createOpen.value = true
}

function openDetail(item) {
  detailProject.value = item
  detailViewer.value = item.viewer || {}
  detailOpen.value = true
}

function onCreated() {
  createOpen.value = false
  fetchProjects()
}

function onChanged(data) {
  if (data && data.project) {
    detailProject.value = { ...data.project, viewer: data.viewer || {} }
    detailViewer.value = data.viewer || {}
  }
  fetchProjects()
}

function onDeleted() {
  detailOpen.value = false
  detailProject.value = null
  fetchProjects()
}

onMounted(() => {
  fetchProjects()
  fetchAccounts()
})

// 登录态变化（登录 / 退出）后重新拉取 viewer 标记与可用账号
watch(
  () => authState.token,
  () => {
    fetchAccounts()
    fetchProjects()
  }
)
</script>

<template>
  <div class="pj-page">
    <Top_navbar />

    <main class="pj-main">
      <header class="pj-hero">
        <div class="pj-hero-text">
          <h1 class="pj-title">
            <FolderKanban :size="26" />
            <span>{{ t('projects.title') }}</span>
          </h1>
          <p class="pj-subtitle">{{ t('projects.subtitle') }}</p>
        </div>
        <button type="button" class="pj-new" :disabled="!online" @click="openCreate">
          <Plus :size="18" />
          <span>{{ t('projects.create') }}</span>
        </button>
      </header>

      <p v-if="!online" class="pj-offline">
        {{ t('projects.serverOffline') }} — {{ t('projects.serverOfflineHint') }}
      </p>

      <nav class="pj-tabs" :aria-label="t('projects.title')">
        <button
          v-for="tab in statusTabs"
          :key="tab.value"
          type="button"
          class="pj-tab"
          :class="{ active: activeStatus === tab.value }"
          @click="activeStatus = tab.value"
        >
          <span>{{ tab.label }}</span>
          <span class="pj-tab-count">{{ tab.count }}</span>
        </button>
      </nav>

      <div v-if="loading" class="pj-loading">
        <span class="spinner"></span>
      </div>

      <div v-else-if="filteredItems.length" class="pj-grid">
        <button
          v-for="item in filteredItems"
          :key="item.name"
          type="button"
          class="pj-card"
          @click="openDetail(item)"
        >
          <div class="pj-card-head">
            <span class="pj-card-title">{{ item.name }}</span>
            <span class="pj-status" :class="item.status">{{ t(statusKey(item.status)) }}</span>
          </div>
          <div class="pj-card-meta">
            <span>{{ t('projects.creator') }}: {{ item.creator || t('projects.none') }}</span>
            <span>{{ t('projects.claimants') }}: {{ item.claimants.length }}</span>
          </div>
          <div v-if="item.created_at" class="pj-card-time">
            {{ t('projects.createdAt') }}: {{ formatTime(item.created_at) }}
          </div>
        </button>
      </div>

      <div v-else class="pj-empty">
        <FolderKanban :size="40" />
        <p>{{ t('projects.empty') }}</p>
        <button v-if="canCreate" type="button" class="pj-new" :disabled="!online" @click="openCreate">
          <Plus :size="18" />
          <span>{{ t('projects.create') }}</span>
        </button>
      </div>
    </main>

    <Page_footer />

    <ProjectCreate
      :open="createOpen"
      :accounts="accounts"
      :default-account="defaultAccount"
      @close="createOpen = false"
      @created="onCreated"
    />

    <ProjectDetail
      :open="detailOpen"
      :project="detailProject"
      :viewer="detailViewer"
      :accounts="accounts"
      :online="online"
      @close="detailOpen = false"
      @changed="onChanged"
      @deleted="onDeleted"
    />
  </div>
</template>

<style scoped>
.pj-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.pj-main {
  width: 100%;
  max-width: 1000px;
  margin: 96px auto 0;
  padding: 0 16px 56px;
  flex: 1;
  box-sizing: border-box;
}

.pj-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.pj-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  color: var(--text-color);
}

.pj-subtitle {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--links-color);
}

.pj-new {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 11px 22px;
  border: none;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.15s ease, transform 0.15s ease;
}

.pj-new:hover {
  background: #d99a1f;
  transform: translateY(-1px);
}

.pj-new:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.pj-new > svg {
  transform: translateY(0.9px);
}

.pj-offline {
  margin: 0 0 16px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(235, 170, 40, 0.14);
  color: #b7791f;
  font-size: 13px;
  line-height: 1.6;
}

.pj-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.pj-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}

.pj-tab:hover {
  background: var(--float-bg);
}

.pj-tab.active {
  border-color: transparent;
  background: var(--text-color);
  color: var(--bg-color);
}

.pj-tab-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}

.pj-loading {
  display: flex;
  justify-content: center;
  padding: 56px 0;
}

.pj-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

.pj-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 18px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 14px;
  background: var(--card-color);
  color: var(--text-color);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.pj-card:hover {
  transform: translateY(-2px);
  border-color: rgba(235, 170, 40, 0.55);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.pj-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.pj-card-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.pj-status {
  flex-shrink: 0;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #1f2937;
}

.pj-status.unclaimed {
  background: #ebaa28;
}

.pj-status.claimed {
  background: #e5484d;
  color: #fff;
}

.pj-status.completed {
  background: #3fb950;
  color: #fff;
}

.pj-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 13px;
  color: var(--links-color);
}

.pj-card-time {
  font-size: 12px;
  color: var(--links-color);
  opacity: 0.85;
}

.pj-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 64px 16px;
  color: var(--links-color);
  text-align: center;
}

.pj-empty svg {
  opacity: 0.5;
}

.pj-empty p {
  margin: 0;
  font-size: 14px;
}

@media (max-width: 768px) {
  .pj-main {
    margin-top: 84px;
    padding-bottom: 40px;
  }

  .pj-title {
    font-size: 21px;
  }

  .pj-grid {
    grid-template-columns: 1fr;
  }
}
</style>

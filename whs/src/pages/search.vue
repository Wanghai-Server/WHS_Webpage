<script setup>
/**
 * 全量搜索页（/search?q=...）。
 *
 * - 一次请求同时搜索 Wiki 页面 + 用户（用户名 / uid / 玩家名 / 昵称 / 小号名）；
 * - 顶部 tabs：Wiki（默认）| 用户，分组展示结果；
 * - 搜索框下方提供"搜索Wiki"按钮，跳转 /wiki/search 专注搜索 Wiki；
 * - 地址栏 q 变化 / 语言切换自动重新搜索。
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search, FileSearch, Users } from 'lucide-vue-next'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import Tabs from '../components/tabs.vue'
import { useWikiLocale } from '../composables/wiki/locale.js'
import { useSiteConfig } from '../composables/useSiteConfig'

const { t } = useI18n()
const { lang } = useWikiLocale()
const route = useRoute()
const router = useRouter()
const siteConfig = useSiteConfig()

const suffix = ref('')
watch([() => siteConfig.value?.title_suffix, lang], () => {
  suffix.value = (siteConfig.value?.title_suffix || {})[lang.value] || ''
}, { immediate: true })

const query = ref(String(route.query.q || ''))
const tab = ref('wiki') // 'wiki' | 'users'
const wikiResults = ref([])
const usersResults = ref([])
const loading = ref(false)
const searched = ref(false)
let timer = null
let seq = 0

async function runSearch() {
  const q = query.value.trim()
  if (!q) {
    wikiResults.value = []
    usersResults.value = []
    searched.value = false
    return
  }
  const current = ++seq
  loading.value = true
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&lang=${lang.value}`)
    const data = await res.json().catch(() => null)
    if (current !== seq) return
    wikiResults.value = (data && data.wiki) || []
    usersResults.value = (data && data.users) || []
    searched.value = true
  } catch {
    if (current !== seq) return
    wikiResults.value = []
    usersResults.value = []
    searched.value = true
  } finally {
    if (current === seq) loading.value = false
  }
}

function onInput() {
  clearTimeout(timer)
  timer = setTimeout(runSearch, 250)
}

// 站点语言切换：用新语言重新搜索
watch(lang, () => {
  if (query.value.trim()) runSearch()
})

// 地址栏 q 变化；immediate：首次进入即自动搜索
watch(
  () => route.query.q,
  (v) => {
    const next = String(v || '')
    if (next !== query.value) query.value = next
    if (query.value.trim()) runSearch()
  },
  { immediate: true }
)

// 文档标题：搜索词 + 站点后缀
watch(query, (v) => {
  document.title = v.trim()
    ? `${v.trim()} - ${t('search.title')}${suffix.value}`
    : `${t('search.title')}${suffix.value}`
}, { immediate: true })

onUnmounted(() => {
  clearTimeout(timer)
  document.title = `${t('search.title')}${suffix.value}`
})

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Tabs（与 user 页同款：金色下滑线 + 平滑滑动）：Wiki | 用户，
// 结果数作为圆形徽章（count）显示在标签右侧
const tabItems = computed(() => [
  { key: 'wiki', label: t('search.wikiTab'), count: wikiResults.value.length || 0 },
  { key: 'users', label: t('search.usersTab'), count: usersResults.value.length || 0 },
])

// "搜索Wiki"按钮：跳转专注搜索
function goWikiSearch() {
  router.push({ path: '/wiki/search', query: { q: query.value.trim() } })
}
</script>

<template>
  <div class="search-page">
    <Top_navbar />

    <main class="search-main">
      <h1 class="search-title">
        <FileSearch :size="22" />
        {{ t('search.title') }}
      </h1>

      <!-- 搜索框 -->
      <div class="search-box">
        <Search :size="18" class="search-icon" />
        <input
          v-model="query"
          type="text"
          class="search-input"
          :placeholder="t('search.placeholder')"
          autofocus
          @input="onInput"
          @keydown.enter="runSearch"
        />
      </div>

      <!-- 动作行：专注搜索 Wiki -->
      <div class="search-actions">
        <button type="button" class="search-mode-btn" @click="goWikiSearch">
          {{ t('search.searchWiki') }}
        </button>
      </div>

      <!-- Tabs：Wiki（默认）| 用户（同 user 页：金色下滑线 + 平滑滑动） -->
      <div v-if="searched && query.trim()" class="search-tabs">
        <Tabs :model-value="tab" :items="tabItems" @update:model-value="tab = $event" />
      </div>

      <!-- 状态 -->
      <div v-if="loading" class="search-state">
        <span class="spinner"></span>
      </div>
      <p v-else-if="searched && !wikiResults.length && !usersResults.length" class="search-state">
        {{ t('search.noResults') }}
      </p>

      <!-- Wiki 结果 -->
      <template v-else-if="tab === 'wiki'">
        <p v-if="wikiResults.length" class="result-group">{{ t('search.wikiLabel') }}</p>
        <ul v-if="wikiResults.length" class="result-list">
          <li v-for="item in wikiResults" :key="item.slug" class="result-item">
            <RouterLink :to="`/wiki/page/${item.slug}`" class="result-link">
              <span class="result-title">{{ item.title || item.slug }}</span>
              <span v-if="item.snippet" class="result-snippet">{{ item.snippet }}</span>
              <span class="result-meta">
                <code class="result-slug">{{ item.slug }}</code>
                <time>{{ formatTime(item.updated_at) }}</time>
              </span>
            </RouterLink>
          </li>
        </ul>
        <p v-else-if="searched" class="search-state">{{ t('search.noResults') }}</p>
      </template>

      <!-- 用户结果 -->
      <template v-else>
        <p v-if="usersResults.length" class="result-group">{{ t('search.usersLabel') }}</p>
        <ul v-if="usersResults.length" class="user-list">
          <li v-for="user in usersResults" :key="user.uid" class="user-item">
            <RouterLink :to="`/user/${user.uid}`" class="user-link">
              <span class="user-head">
                <Users :size="18" class="user-avatar" />
                <span class="user-username">{{ user.username }}</span>
                <code class="user-uid">#{{ user.uid }}</code>
              </span>
              <span class="user-detail">
                <span v-if="user.fullname" class="user-field">
                  {{ t('search.fullname') }}：{{ user.fullname }}
                </span>
                <span v-if="user.player_name" class="user-field">
                  {{ t('search.playerName') }}：{{ user.player_name }}
                </span>
                <span v-if="user.alts && user.alts.length" class="user-field">
                  {{ t('search.altAccounts') }}：
                  <em v-for="alt in user.alts" :key="alt" class="user-alt">{{ alt }}</em>
                </span>
              </span>
            </RouterLink>
          </li>
        </ul>
        <p v-else-if="searched" class="search-state">{{ t('search.noResults') }}</p>
      </template>
    </main>

    <Page_footer />
  </div>
</template>

<style scoped>
.search-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.search-main {
  width: 100%;
  max-width: 820px;
  min-width: 0;
  margin: 96px auto 0;
  /* 底部留白：与底部导航栏之间保持空隙（同 wiki 布局 48px） */
  padding: 0 16px 48px;
  flex: 1;
}

.search-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 18px;
  font-size: 20px;
  font-weight: 800;
  color: var(--text-color);
}

/* 搜索框 */
.search-box {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--float-bg);
  border-radius: 999px;
  background: var(--card-color);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.search-box:focus-within {
  border-color: var(--notice-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--notice-color) 25%, transparent);
}

.search-icon {
  flex-shrink: 0;
  color: var(--links-color);
  margin-left: 18px;
}

.search-input {
  flex: 1;
  min-width: 0;
  padding: 13px 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-color);
  font-size: 16px;
}

/* 动作行 */
.search-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.search-mode-btn {
  padding: 7px 16px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.search-mode-btn:hover {
  background: var(--float-bg);
  color: var(--text-color);
  border-color: var(--notice-color);
}

/* Tabs（底条与滑动逻辑由 components/tabs.vue 提供） */
.search-tabs {
  margin-top: 22px;
}

.search-state {
  min-height: 30vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--links-color);
}

.spinner {
  width: 26px;
  height: 26px;
  border: 3px solid var(--float-bg);
  border-top-color: var(--notice-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.result-group {
  margin: 20px 2px 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--links-color);
}

/* Wiki 结果 */
.result-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.result-item {
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
  overflow: hidden;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.result-item:hover {
  border-color: var(--notice-color);
  transform: translateY(-1px);
}

.result-link {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 18px;
  text-decoration: none;
}

.result-title {
  font-size: 15.5px;
  font-weight: 700;
  color: var(--text-color);
}

.result-snippet {
  font-size: 13px;
  line-height: 1.6;
  color: var(--links-color);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--links-color);
}

.result-slug {
  padding: 1px 8px;
  border-radius: 6px;
  background: var(--float-bg);
  font-family: Consolas, 'Courier New', monospace;
}

/* 用户结果 */
.user-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.user-item {
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
  overflow: hidden;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.user-item:hover {
  border-color: var(--notice-color);
  transform: translateY(-1px);
}

.user-link {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 18px;
  text-decoration: none;
}

.user-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 34px;
  height: 34px;
  padding: 7px;
  box-sizing: border-box;
  border-radius: 999px;
  background: var(--float-bg);
  color: var(--links-color);
}

.user-username {
  font-size: 15.5px;
  font-weight: 700;
  color: var(--text-color);
}

.user-uid {
  padding: 1px 8px;
  border-radius: 6px;
  background: var(--float-bg);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  color: var(--links-color);
}

.user-detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--links-color);
}

.user-field {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.user-alt {
  font-style: normal;
  padding: 0 7px;
  border-radius: 6px;
  background: var(--float-bg);
  color: var(--text-color);
  font-size: 12px;
  line-height: 20px;
}
</style>

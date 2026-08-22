<script setup>
/**
 * 维基搜索结果页（/wiki/search?q=...）。
 *
 * - 搜索框防抖实时搜索（按当前语言请求后端），回车立即搜索；
 * - 地址栏 q 变化（首页搜索跳转 / 分享链接 / 语言切换）自动重新搜索；
 * - 展示全部结果（标题 / 摘要 / 路径 / 更新时间），点击进入阅读页。
 */
import { ref, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search, ArrowLeft, FileSearch } from 'lucide-vue-next'
import { wikiApi } from '../../composables/wiki/api.js'
import { useWikiLocale } from '../../composables/wiki/locale.js'
import { useSiteConfig } from '../../composables/useSiteConfig'

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
const results = ref([])
const loading = ref(false)
const searched = ref(false)
let timer = null
let seq = 0

async function runSearch() {
  const q = query.value.trim()
  if (!q) {
    results.value = []
    searched.value = false
    return
  }
  const current = ++seq
  loading.value = true
  try {
    const data = await wikiApi.search(q, lang.value)
    if (current !== seq) return
    results.value = data.results || []
    searched.value = true
  } catch {
    if (current !== seq) return
    results.value = []
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

// 地址栏 q 变化（首页"查看全部结果"跳转 / 直接访问链接）；
// immediate：首次进入即自动搜索，无需再按回车
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
    ? `${v.trim()} - ${t('pages.wiki.search.resultsTitle')}${suffix.value}`
    : `${t('pages.wiki.title')}${suffix.value}`
}, { immediate: true })

onUnmounted(() => {
  clearTimeout(timer)
  document.title = `${t('pages.wiki.title')}${suffix.value}`
})

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function back() {
  router.push('/wiki')
}

// "全量搜索"按钮：跳转站级全量搜索页（Wiki + 用户）
function goFull() {
  router.push({ path: '/search', query: { q: query.value.trim() } })
}
</script>

<template>
  <div class="search-page">
    <header class="search-head">
      <button type="button" class="back-btn" @click="back">
        <ArrowLeft :size="16" />
        {{ t('pages.wiki.actions.back') }}
      </button>
      <h1 class="search-title">
        <FileSearch :size="20" />
        {{ t('pages.wiki.search.resultsTitle') }}
      </h1>
    </header>

    <!-- 搜索框 -->
    <div class="search-box">
      <Search :size="18" class="search-icon" />
      <input
        v-model="query"
        type="text"
        class="search-input"
        :placeholder="t('pages.wiki.search.placeholder')"
        autofocus
        @input="onInput"
        @keydown.enter="runSearch"
      />
    </div>

    <!-- 动作行：全量搜索 -->
    <div class="search-actions">
      <button type="button" class="search-mode-btn" @click="goFull">
        {{ t('search.fullSearch') }}
      </button>
    </div>

    <!-- 状态 -->
    <div v-if="loading" class="search-state">
      <span class="spinner"></span>
    </div>
    <p v-else-if="searched && !results.length" class="search-state">
      {{ t('pages.wiki.search.noResults') }}
    </p>

    <!-- 全部结果 -->
    <ul v-else-if="results.length" class="result-list">
      <li v-for="item in results" :key="item.slug" class="result-item">
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
  </div>
</template>

<style scoped>
.search-page {
  max-width: 760px;
  min-width: 0;
  /* 全宽内容区中水平居中 */
  margin: 0 auto;
  padding: 0 16px;
}

.search-head {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.back-btn:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.search-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
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

.search-state {
  min-height: 30vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--links-color);
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

/* 结果列表 */
.result-list {
  list-style: none;
  margin: 18px 0 0;
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
</style>

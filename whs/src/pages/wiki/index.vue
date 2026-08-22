<script setup>
/**
 * 维基首页：大搜索 + 知识分组（slug 首段）+ 最近更新时间线。
 * 全部界面文案与页面标题按当前语言从后端实时获取。
 */
import { ref, inject, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, History, FolderOpen, Sparkles, RefreshCw } from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'
import { useWikiLocale } from '../../composables/wiki/locale.js'
import { wikiApi } from '../../composables/wiki/api.js'
import WikiSearch from '../../components/wiki/wiki_search.vue'

const { t } = useI18n()
const { lang } = useWikiLocale()
const router = useRouter()
const { state: authState } = useAuth()

// 页面清单由 layout 统一加载并提供（语言切换时标题自动重算）
const pages = inject('wikiPages', ref([]))

const canWrite = computed(
  () => !!authState.user && (authState.user.permission || 0) >= 2
)

function pageTitle(page) {
  const primary = lang.value === 'en' ? page.title_en : page.title_zh
  const fallback = lang.value === 'en' ? page.title_zh : page.title_en
  return primary || fallback || page.slug
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// 分组：按 slug 第一段聚合
const groups = computed(() => {
  const map = new Map()
  for (const page of pages.value) {
    const segs = String(page.slug).split('/')
    const group = segs.length > 1 ? segs[0] : ''
    if (!map.has(group)) map.set(group, [])
    map.get(group).push(page)
  }
  return [...map.entries()]
    .map(([name, list]) => ({ name, list }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

// 最近更新（最多 6 条）
const recent = computed(() =>
  [...pages.value]
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
    .slice(0, 6)
)

// 今日词条：每次挂载时从维基库随机抽取一个词条，可点击刷新换一个
const wordOfDay = ref(null)
const wordContent = ref('')
let wordSeq = 0

function pickWordOfDay() {
  const pool = pages.value.filter((p) => p.slug !== (wordOfDay.value && wordOfDay.value.slug))
  const candidates = pool.length ? pool : pages.value
  if (!candidates.length) {
    wordOfDay.value = null
    wordContent.value = ''
    return
  }
  wordOfDay.value = candidates[Math.floor(Math.random() * candidates.length)]
}

// 拉取词条正文（按当前语言；异步竞态用序号 + slug 双重校验）
async function loadWordContent() {
  const current = ++wordSeq
  if (!wordOfDay.value) return
  const slug = wordOfDay.value.slug
  try {
    const data = await wikiApi.getPage(slug, lang.value)
    if (current !== wordSeq || !wordOfDay.value || wordOfDay.value.slug !== slug) return
    wordContent.value = data.page ? data.page.content || '' : ''
  } catch {
    if (current === wordSeq) wordContent.value = ''
  }
}

// 词条摘要：剥离 Markdown 标记后截断（超长只显示部分）
const excerpt = computed(() => {
  const text = wordContent.value
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/[#>*_~|-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > 150 ? `${text.slice(0, 150)}…` : text
})

// 页面清单异步到达后抽取；每次挂载（immediate）重新随机抽取；
// 词条或语言变化时重新拉取正文
watch(pages, () => pickWordOfDay(), { immediate: true })
watch([wordOfDay, lang], () => loadWordContent())

function newPage() {
  router.push({ path: '/wiki/edit' })
}
</script>

<template>
  <div class="wiki-home">
    <!-- Hero：大搜索 -->
    <section class="home-hero load-in">
      <h1 class="hero-title">{{ t('pages.wiki.title') }}</h1>
      <p class="hero-subtitle">{{ t('pages.wiki.description') }}</p>
      <div class="hero-search">
        <WikiSearch size="large" />
      </div>
      <button v-if="canWrite" type="button" class="hero-new" @click="newPage">
        <Plus :size="16" />
        {{ t('pages.wiki.actions.newPage') }}
      </button>
    </section>

    <!-- 空态 -->
    <section v-if="!groups.length" class="home-empty load-in" style="--load-delay: 120ms">
      <p>{{ t('pages.wiki.home.empty') }}</p>
    </section>

    <!-- 知识分组 -->
    <section v-else class="home-section load-in" style="--load-delay: 120ms">
      <h2 class="section-title">
        <FolderOpen :size="18" />
        {{ t('pages.wiki.home.groups') }}
      </h2>
      <div class="group-grid">
        <div v-for="group in groups" :key="group.name || '_root'" class="group-card">
          <header class="group-head">
            <h3 class="group-name">{{ group.name || '/' }}</h3>
            <span class="group-count">{{ group.list.length }} {{ t('pages.wiki.home.pages') }}</span>
          </header>
          <ul class="group-list">
            <li v-for="page in group.list" :key="page.slug">
              <RouterLink :to="`/wiki/page/${page.slug}`" class="group-link">
                {{ pageTitle(page) }}
              </RouterLink>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <!-- 最近更新 -->
    <section v-if="recent.length" class="home-section load-in" style="--load-delay: 200ms">
      <h2 class="section-title">
        <History :size="18" />
        {{ t('pages.wiki.home.recent') }}
      </h2>
      <ul class="recent-list">
        <li v-for="page in recent" :key="page.slug">
          <RouterLink :to="`/wiki/page/${page.slug}`" class="recent-link">
            <span class="recent-title">{{ pageTitle(page) }}</span>
            <span class="recent-slug">{{ page.slug }}</span>
            <time class="recent-time">{{ formatTime(page.updated_at) }}</time>
          </RouterLink>
        </li>
      </ul>
    </section>

    <!-- 今日词条（每次挂载随机抽取，可刷新） -->
    <section v-if="wordOfDay" class="home-section load-in" style="--load-delay: 280ms">
      <div class="section-head">
        <h2 class="section-title">
          <Sparkles :size="18" />
          {{ t('pages.wiki.home.wordOfDay') }}
        </h2>
        <button
          type="button"
          class="word-refresh"
          :title="t('pages.wiki.home.wordRefresh')"
          :aria-label="t('pages.wiki.home.wordRefresh')"
          @click="pickWordOfDay"
        >
          <RefreshCw :size="15" />
        </button>
      </div>

      <RouterLink :to="`/wiki/page/${wordOfDay.slug}`" class="word-card">
        <!-- 左侧：标题 -->
        <div class="word-left">
          <span class="word-title">{{ pageTitle(wordOfDay) }}</span>
          <code class="word-slug">{{ wordOfDay.slug }}</code>
        </div>
        <!-- 右侧：内容摘要（超长截断）+ 编辑时间 -->
        <div class="word-right">
          <span class="word-excerpt">{{ excerpt || '—' }}</span>
          <span class="word-meta">
            <time>{{ formatTime(wordOfDay.updated_at) }}</time>
          </span>
        </div>
      </RouterLink>
    </section>
  </div>
</template>

<style scoped>
.wiki-home {
  max-width: 860px;
  /* 全宽内容区中水平居中 */
  margin: 0 auto;
  padding: 0 16px;
}

/* Hero */
.home-hero {
  padding: 32px 0 40px;
  text-align: center;
}

.hero-title {
  margin: 0 0 10px;
  font-size: 40px;
  font-weight: 800;
  color: var(--text-color);
}

.hero-subtitle {
  margin: 0 auto 28px;
  max-width: 560px;
  font-size: 15px;
  line-height: 1.8;
  color: var(--links-color);
}

.hero-search {
  max-width: 520px;
  margin: 0 auto;
}

.hero-new {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 22px;
  padding: 9px 20px;
  border: 1px dashed var(--notice-color);
  border-radius: 999px;
  background: transparent;
  color: var(--text-color);
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.hero-new:hover {
  background: var(--float-bg);
}

/* 通用 section */
.home-section {
  margin-top: 8px;
}

/* 区块头部：标题在最左，操作按钮在最右 */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.section-head .section-title {
  margin: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 16px;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-color);
}

.section-title :deep(svg) {
  color: var(--links-color);
}

/* 今日词条：刷新按钮（标题对侧，贴最右）；旋转只作用于图标，背景保持不动 */
.word-refresh {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.word-refresh:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.word-refresh :deep(svg) {
  transition: transform 0.25s ease;
}

.word-refresh:active :deep(svg) {
  transform: rotate(-180deg);
}

/* 今日词条卡片：左标题 / 右内容摘要 + 编辑时间 */
.word-card {
  display: flex;
  align-items: stretch;
  gap: 16px;
  padding: 14px 18px;
  border: 1px solid rgba(235, 170, 40, 0.3);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(235, 170, 40, 0.1), rgba(235, 170, 40, 0.03));
  text-decoration: none;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.word-card:hover {
  border-color: var(--notice-color);
  transform: translateY(-2px);
}

.word-left {
  flex-shrink: 0;
  width: 200px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding-right: 16px;
  border-right: 1px dashed rgba(235, 170, 40, 0.35);
}

.word-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.word-slug {
  font-size: 12px;
  color: var(--links-color);
  opacity: 0.8;
  word-break: break-all;
}

.word-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.word-excerpt {
  font-size: 13px;
  line-height: 1.6;
  color: var(--links-color);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.word-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--links-color);
}

@media (max-width: 560px) {
  .word-card {
    flex-direction: column;
    gap: 10px;
  }

  .word-left {
    width: auto;
    padding-right: 0;
    padding-bottom: 10px;
    border-right: none;
    border-bottom: 1px dashed rgba(235, 170, 40, 0.35);
  }
}

.home-empty {
  padding: 64px 0;
  text-align: center;
  color: var(--links-color);
  font-size: 15px;
}

/* 分组卡片 */
.group-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.group-card {
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
  padding: 16px;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.group-card:hover {
  border-color: var(--notice-color);
  transform: translateY(-2px);
}

.group-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.group-name {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-color);
}

.group-count {
  font-size: 12px;
  color: var(--links-color);
  white-space: nowrap;
}

.group-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.group-link {
  display: block;
  padding: 4px 0;
  color: var(--links-color);
  font-size: 13.5px;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.12s ease;
}

.group-link:hover {
  color: var(--text-color);
}

/* 最近更新 */
.recent-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  overflow: hidden;
}

.recent-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 16px;
  text-decoration: none;
  border-bottom: 1px solid var(--float-bg);
  transition: background-color 0.12s ease;
}

.recent-list li:last-child .recent-link {
  border-bottom: none;
}

.recent-link:hover {
  background: var(--float-bg);
}

.recent-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-slug {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--links-color);
  opacity: 0.8;
}

.recent-time {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 12px;
  color: var(--links-color);
}

@media (max-width: 560px) {
  .hero-title {
    font-size: 30px;
  }

  .recent-slug {
    display: none;
  }
}
</style>

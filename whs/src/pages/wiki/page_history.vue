<script setup>
/**
 * 修订历史：按语言展示该页面的修订时间线，可查看任意版本内容，管理员可回滚。
 */
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, RotateCcw, FileClock } from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'
import { useDialogBox } from '../../composables/useDialogBox'
import { wikiApi } from '../../composables/wiki/api.js'
import { useWikiLocale } from '../../composables/wiki/locale.js'
import WikiMarkdown from '../../components/wiki/wiki_markdown.vue'

const { t } = useI18n()
const { lang } = useWikiLocale()
const route = useRoute()
const router = useRouter()
const { state: authState } = useAuth()
const dialogBox = useDialogBox()

const slug = computed(() => String(route.params.slug || ''))
// 修订语言跟随站点语言（底部导航栏切换），不提供页内切换器

const loading = ref(true)
const notFound = ref(false)
const pageMeta = ref(null)
const revisions = ref([])
const selectedRev = ref(null) // 当前查看的修订 id；null = 最新
const viewingRev = ref(null) // 正在展示的修订数据

// 是否可回滚：按页面自身的最小编辑权限校验
const canRestore = computed(() => {
  if (!authState.user || !pageMeta.value) return false
  return (authState.user.permission || 0) >= (pageMeta.value.min_permission || 2)
})

async function loadHistory() {
  loading.value = true
  notFound.value = false
  try {
    const data = await wikiApi.getHistory(slug.value, lang.value)
    pageMeta.value = data.page
    revisions.value = data.revisions || []
    if (revisions.value.length) {
      selectedRev.value = revisions.value[0].id
      await loadRevision(revisions.value[0].id)
    } else {
      selectedRev.value = null
      viewingRev.value = null
    }
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

async function loadRevision(revId) {
  try {
    const data = await wikiApi.getRevision(revId)
    viewingRev.value = data.revision
  } catch {
    viewingRev.value = null
  }
}

function selectRev(rev) {
  selectedRev.value = rev.id
  loadRevision(rev.id)
}

// 站点语言切换 → 重新拉取对应语言的修订
watch(lang, () => loadHistory(), { immediate: true })

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function authorName(rev) {
  return rev.author_name || t('pages.wiki.meta.system')
}

async function restore() {
  if (!viewingRev.value) return
  const ok = await dialogBox.confirm({
    title: t('pages.wiki.actions.restore'),
    message: t('pages.wiki.history.restoreConfirm'),
    confirmText: t('pages.wiki.actions.restore'),
  })
  if (!ok) return
  try {
    await wikiApi.restoreRevision(viewingRev.value.id)
    router.push(`/wiki/page/${slug.value}`)
  } catch {
    /* 恢复失败保持原状 */
  }
}

function backToPage() {
  router.push(`/wiki/page/${slug.value}`)
}
</script>

<template>
  <div class="history-page">
    <header class="history-head">
      <button type="button" class="back-btn" @click="backToPage">
        <ArrowLeft :size="16" />
        {{ t('pages.wiki.history.backToPage') }}
      </button>
      <h1 class="history-title">
        <FileClock :size="20" />
        {{ t('pages.wiki.history.title') }}
      </h1>
    </header>

    <div v-if="loading" class="history-state">
      <span class="spinner"></span>
    </div>

    <p v-else-if="notFound" class="history-state">
      {{ t('pages.wiki.notFound.title') }}
    </p>

    <div v-else-if="revisions.length" class="history-body">
      <!-- 修订列表 -->
      <ul class="rev-list">
        <li v-for="rev in revisions" :key="rev.id">
          <button
            type="button"
            class="rev-item"
            :class="{ active: rev.id === selectedRev }"
            @click="selectRev(rev)"
          >
            <div class="rev-line">
              <span class="rev-no">{{ t('pages.wiki.meta.rev') }} {{ rev.rev_no }}</span>
              <span v-if="rev.rev_no === pageMeta.rev_no" class="rev-current">
                {{ t('pages.wiki.history.current') }}
              </span>
            </div>
            <div class="rev-meta">
              <span>{{ authorName(rev) }}</span>
              <time>{{ formatTime(rev.created_at) }}</time>
            </div>
            <p v-if="rev.summary" class="rev-summary">{{ rev.summary }}</p>
          </button>
        </li>
      </ul>

      <!-- 版本预览 -->
      <div class="rev-viewer">
        <div v-if="viewingRev" class="viewer-head">
          <span class="viewer-title">
            {{ t('pages.wiki.history.viewing') }}
            {{ t('pages.wiki.meta.rev') }} {{ viewingRev.rev_no }}
          </span>
          <!-- 浏览当前版本时无需"恢复此版本" -->
          <button
            v-if="canRestore && viewingRev.rev_no !== pageMeta.rev_no"
            type="button"
            class="restore-btn"
            @click="restore"
          >
            <RotateCcw :size="14" />
            {{ t('pages.wiki.actions.restore') }}
          </button>
        </div>
        <div class="viewer-body">
          <WikiMarkdown :content="viewingRev.content || ''" />
        </div>
      </div>
    </div>

    <p v-else class="history-state">
      {{ t('pages.wiki.history.empty') }}
    </p>
  </div>
</template>

<style scoped>
.history-page {
  min-width: 0;
  /* 全宽内容区中水平居中 */
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 24px;
}

.history-head {
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
  text-decoration: none;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.back-btn:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.history-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: var(--text-color);
}

.history-state {
  min-height: 40vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--links-color);
}

.history-body {
  display: grid;
  grid-template-columns: minmax(240px, 320px) 1fr;
  gap: 18px;
  align-items: start;
}

/* 修订列表 */
.rev-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: calc(100vh - 220px);
  overflow-y: auto;
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
}

.rev-item {
  display: block;
  width: 100%;
  box-sizing: border-box;
  padding: 11px 14px;
  border: none;
  border-bottom: 1px solid var(--float-bg);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.rev-list li:last-child .rev-item {
  border-bottom: none;
}

.rev-item:hover {
  background: var(--float-bg);
}

.rev-item.active {
  background: var(--float-bg);
  box-shadow: inset 3px 0 0 var(--notice-color);
}

.rev-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rev-no {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-color);
}

.rev-current {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--notice-color);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-color);
}

.rev-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--links-color);
}

.rev-summary {
  margin: 6px 0 0;
  font-size: 12.5px;
  color: var(--links-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 版本预览 */
.rev-viewer {
  min-width: 0;
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
  overflow: hidden;
}

.viewer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--float-bg);
}

.viewer-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--links-color);
}

.restore-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: none;
  border-radius: 9px;
  background: var(--notice-color);
  color: var(--text-color);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s ease;
}

.restore-btn:hover {
  filter: brightness(1.06);
}

.viewer-body {
  padding: 18px 22px;
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

@media (max-width: 1023px) {
  .history-page {
    padding: 0 16px;
  }
}

@media (max-width: 860px) {
  .history-body {
    grid-template-columns: 1fr;
  }

  .rev-list {
    max-height: 40vh;
  }
}
</style>

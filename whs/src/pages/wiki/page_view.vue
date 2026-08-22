<script setup>
/**
 * 维基阅读页：按语言从后端拉取 Markdown 原文并渲染。
 *
 * - 语言切换实时生效：站点语言变化（documentElement.lang）或页内语言
 *   切换器变化都会触发向后端重新请求对应语言的内容；
 * - 右侧大纲（TOC）由 wiki_markdown 从标题自动解析并滚动联动；
 * - 展示历史贡献者（谁编写过该页面、各编辑几次）；
 * - 管理员可编辑 / 查看历史 / 删除。
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Pencil, History, Trash2, ChevronRight, Lock, ListTree } from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'
import { useSiteConfig } from '../../composables/useSiteConfig'
import { useTips } from '../../composables/useTips'
import { useDialogBox } from '../../composables/useDialogBox'
import { wikiApi, WikiApiError } from '../../composables/wiki/api.js'
import { useWikiLocale, LANG_LABELS } from '../../composables/wiki/locale.js'
import WikiMarkdown from '../../components/wiki/wiki_markdown.vue'
import WikiOutline from '../../components/wiki/wiki_outline.vue'
import WikiPage404 from '../../components/wiki/wiki_page_404.vue'

const { t } = useI18n()
const { lang } = useWikiLocale()
const route = useRoute()
const router = useRouter()
const { state: authState } = useAuth()
const siteConfig = useSiteConfig()
const { showTip } = useTips()
const dialogBox = useDialogBox()

const slug = computed(() => String(route.params.slug || ''))
// 内容语言跟随站点语言（底部导航栏切换），不提供页内切换器

const page = ref(null)
const outline = ref([])
const loading = ref(true)
const notFound = ref(false)
const loadError = ref(false)

const canWrite = computed(
  () => !!authState.user && (authState.user.permission || 0) >= 2
)

// 管理员：可调整页面最小编辑权限（2/3/4）
const isAdmin = computed(() => !!authState.user && (authState.user.permission || 0) >= 3)

const myPermission = computed(() => (authState.user ? authState.user.permission || 0 : 0))

// 是否可编辑当前页面（按页面自身的最小编辑权限校验）
const canEditPage = computed(() => {
  if (!canWrite.value || !page.value) return false
  return myPermission.value >= (page.value.min_permission || 2)
})

// 是否可调整本页编辑权限：管理员且可操作当前等级（与 admin 的 canSetPermission 一致）
const canManagePermission = computed(
  () => isAdmin.value && !!page.value && myPermission.value >= (page.value.min_permission || 2)
)

const permissionSaving = ref(false)

async function changePermission(value) {
  if (!isAdmin.value || !page.value || permissionSaving.value) return
  // 不能操作更高编辑权限等级的页面（与 admin 的 cannotManageHigher 一致）
  if (myPermission.value < (page.value.min_permission || 2)) {
    showTip('warning', t('pages.wiki.permission.cannotManageHigher'))
    return
  }
  // 不能把页面权限设置得高于自己的权限（与 admin 的 newPermissionHigher 一致）
  if (value > myPermission.value) {
    showTip('warning', t('pages.wiki.permission.newPermissionHigher'))
    return
  }
  permissionSaving.value = true
  try {
    await wikiApi.setPermission(page.value.slug, value)
    page.value.min_permission = value
    showTip('info', t('pages.wiki.permission.updated'))
  } catch (err) {
    showTip('error', err instanceof Error ? err.message : t('pages.wiki.loadError'))
  } finally {
    permissionSaving.value = false
  }
}

// 语言回退标题（页面缺失当前语言时，用另一语言标题兜底展示）
const fallbackTitle = computed(() => {
  if (!page.value) return ''
  const other = lang.value === 'en' ? 'zh' : 'en'
  return lang.value === 'en'
    ? page.value.title_en || page.value.title_zh
    : page.value.title_zh || page.value.title_en
})

const displayTitle = computed(() => page.value?.title || fallbackTitle.value || slug.value)

const langNotice = computed(() => {
  if (!page.value) return ''
  const others = (page.value.available_langs || []).filter((l) => l !== lang.value)
  if (page.value.content || !others.length) return ''
  return t('pages.wiki.meta.langNotice', {
    lang: LANG_LABELS[lang.value] || lang.value,
    other: LANG_LABELS[others[0]] || others[0],
  })
})

const breadcrumbs = computed(() => {
  const segs = slug.value.split('/')
  let acc = ''
  return segs.map((seg) => {
    acc = acc ? `${acc}/${seg}` : seg
    return { name: seg, path: acc }
  })
})

const suffix = computed(() => (siteConfig.value?.title_suffix || {})[lang.value] || '')

async function loadPage() {
  loading.value = true
  notFound.value = false
  loadError.value = false
  try {
    const data = await wikiApi.getPage(slug.value, lang.value)
    if (data.redirect) {
      // 旧路径重定向：路由替换到新路径（URL 同步更新，避免 404）
      router.replace(`/wiki/page/${data.redirect}`)
      return
    }
    page.value = data.page
  } catch (err) {
    if (err instanceof WikiApiError && err.code === 'wiki_page_not_found') {
      notFound.value = true
      page.value = null
    } else {
      loadError.value = true
    }
  } finally {
    loading.value = false
  }
}

// 站点语言切换 / 首次加载 / slug 变化 → 重新请求对应语言的内容
watch([lang, slug], () => {
  loadPage()
}, { immediate: true })

// 文档标题：页面标题 + 站点后缀（当前语言）
watch([page, lang], () => {
  if (page.value) {
    document.title = `${displayTitle.value}${suffix.value}`
  }
}, { immediate: true })

onUnmounted(() => {
  document.title = `${t('pages.wiki.title')}${suffix.value}`
})

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function contributorName(c) {
  return c.name || t('pages.wiki.meta.system')
}

async function removePage() {
  const ok = await dialogBox.confirm({
    title: t('pages.wiki.actions.delete'),
    message: t('pages.wiki.confirmDelete'),
    confirmText: t('pages.wiki.actions.delete'),
    danger: true,
  })
  if (!ok) return
  try {
    await wikiApi.deletePage(slug.value)
    router.push('/wiki')
  } catch {
    /* 删除失败保持原页 */
  }
}
</script>

<template>
  <div class="page-layout">
    <div class="page-main">
      <!-- 加载中 -->
      <div v-if="loading" class="page-state">
        <span class="spinner"></span>
      </div>

      <!-- 加载失败 -->
      <div v-else-if="loadError" class="page-state">
        <p>{{ t('pages.wiki.loadError') }}</p>
      </div>

      <!-- 页面不存在 -->
      <WikiPage404 v-else-if="notFound" :slug="slug" />

      <template v-else-if="page">
        <!-- 面包屑 -->
        <nav class="crumbs" aria-label="Breadcrumb">
          <RouterLink to="/wiki" class="crumb">{{ t('pages.wiki.title') }}</RouterLink>
          <template v-for="(crumb, i) in breadcrumbs" :key="crumb.path">
            <ChevronRight :size="13" class="crumb-sep" />
            <RouterLink
              v-if="i < breadcrumbs.length - 1"
              :to="`/wiki/page/${crumb.path}`"
              class="crumb"
            >
              {{ crumb.name }}
            </RouterLink>
            <span v-else class="crumb current">{{ crumb.name }}</span>
          </template>
        </nav>

        <!-- 消歧义页提示 -->
        <div v-if="page.disambig" class="disambig-banner">
          <ListTree :size="16" />
          <span>{{ t('pages.wiki.disambig.banner') }}</span>
        </div>

        <!-- 当前语言缺失提示（语言切换统一走底部导航栏） -->
        <div v-if="langNotice" class="lang-notice">{{ langNotice }}</div>

        <!-- 正文 -->
        <article class="article">
          <WikiMarkdown :content="page.content" @outline="outline = $event" />
        </article>

        <!-- 元信息卡：时间 / 版本 / 贡献者 / 编辑权限 -->
        <footer class="meta-card">
          <div class="meta-row">
            <span>{{ t('pages.wiki.meta.lastUpdated') }}: {{ formatTime(page.updated_at) }}</span>
            <span class="dot">·</span>
            <span>{{ t('pages.wiki.meta.rev') }} {{ page.rev_no }}</span>
            <span class="dot">·</span>
            <span>{{ page.revisions_count }} {{ t('pages.wiki.meta.revisions') }}</span>
          </div>

          <!-- 管理员：调整本页最小编辑权限（可操作当前等级；高等级页面不显示） -->
          <div v-if="canManagePermission" class="perm-row">
            <span class="perm-label">
              <Lock :size="13" />
              {{ t('pages.wiki.meta.minPermission') }}
            </span>
            <div class="perm-pills">
              <button
                v-for="v in [2, 3, 4]"
                :key="v"
                type="button"
                class="perm-pill"
                :class="{ active: (page.min_permission || 2) === v }"
                :disabled="permissionSaving"
                @click="changePermission(v)"
              >
                {{ t(`pages.wiki.permission.levels.${v}`) }}
              </button>
            </div>
          </div>

          <div v-if="page.contributors && page.contributors.length" class="contrib-row">
            <span class="contrib-label">{{ t('pages.wiki.meta.contributors') }}</span>
            <span v-for="c in page.contributors" :key="c.author_uid" class="contrib-chip">
              {{ contributorName(c) }}
              <em v-if="c.edit_count > 1">×{{ c.edit_count }}</em>
            </span>
          </div>
        </footer>

        <!-- 管理员操作 -->
        <div v-if="canEditPage" class="admin-actions">
          <RouterLink :to="`/wiki/edit/${page.slug}`" class="admin-btn">
            <Pencil :size="15" />
            {{ t('pages.wiki.actions.edit') }}
          </RouterLink>
          <RouterLink :to="`/wiki/history/${page.slug}`" class="admin-btn">
            <History :size="15" />
            {{ t('pages.wiki.actions.history') }}
          </RouterLink>
          <button type="button" class="admin-btn danger" @click="removePage">
            <Trash2 :size="15" />
            {{ t('pages.wiki.actions.delete') }}
          </button>
        </div>
      </template>
    </div>

    <!-- 右侧大纲 -->
    <aside class="page-rail">
      <WikiOutline :items="outline" />
    </aside>
  </div>
</template>

<style scoped>
.page-layout {
  display: flex;
  gap: 36px;
  align-items: flex-start;
  /* 仅左侧留白：右侧大纲贴住屏幕右缘 */
  padding-left: 24px;
}

.page-main {
  flex: 1;
  min-width: 0;
  max-width: 760px;
  /* 超出最大宽度后在剩余空间居中 */
  margin: 0 auto;
  padding-bottom: 48px;
}

.page-rail {
  /* 粘性侧栏：跟随滚动时固定在视口内，具备"当前页面导航"作用；
     作为 .page-layout 的最右列，随全宽内容区延伸至屏幕右缘 */
  position: sticky;
  top: 96px;
  align-self: flex-start;
  flex-shrink: 0;
  width: 190px;
  max-height: calc(100vh - 140px);
  overflow-y: auto;
  display: none;
}

/* 视口足够宽（文章列 + 大纲 190 + 间距）时才显示，大纲贴屏幕右缘 */
@media (min-width: 1100px) {
  .page-rail {
    display: block;
  }
}

@media (max-width: 1023px) {
  .page-layout {
    padding: 0 16px;
  }
}

.page-state {
  min-height: 50vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--links-color);
}

/* 面包屑 */
.crumbs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 18px;
  font-size: 13px;
}

.crumb {
  color: var(--links-color);
  text-decoration: none;
  transition: color 0.12s ease;
}

.crumb:hover {
  color: var(--text-color);
}

.crumb.current {
  color: var(--text-color);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.crumb-sep {
  color: var(--links-color);
  opacity: 0.6;
}

/* 消歧义页横幅 */
.disambig-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--float-bg);
  color: var(--links-color);
  font-size: 13px;
  line-height: 1.6;
}

.disambig-banner :deep(svg) {
  flex-shrink: 0;
  color: var(--notice-color);
}

/* 当前语言缺失提示 */
.lang-notice {
  margin-bottom: 14px;
  padding: 9px 14px;
  border-radius: 10px;
  background: var(--float-bg);
  color: var(--links-color);
  font-size: 13px;
}

.article {
  min-width: 0;
}

/* 元信息卡 */
.meta-card {
  margin-top: 40px;
  padding: 14px 16px;
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
  font-size: 12.5px;
  color: var(--links-color);
}

.meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.dot {
  opacity: 0.5;
}

.perm-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--float-bg);
}

.perm-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 600;
}

.perm-pills {
  display: flex;
  gap: 4px;
}

.perm-pill {
  padding: 3px 12px;
  border: 1px solid var(--float-bg);
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.perm-pill:hover:not(:disabled) {
  color: var(--text-color);
}

.perm-pill.active {
  border-color: var(--notice-color);
  background: var(--float-bg);
  color: var(--text-color);
  font-weight: 600;
}

.perm-pill:disabled {
  opacity: 0.6;
  cursor: default;
}

.contrib-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--float-bg);
}

.contrib-label {
  font-weight: 600;
}

.contrib-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--float-bg);
  color: var(--text-color);
}

.contrib-chip em {
  font-style: normal;
  opacity: 0.6;
  font-size: 11px;
}

/* 管理员操作 */
.admin-actions {
  display: flex;
  gap: 8px;
  margin-top: 20px;
}

.admin-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--text-color);
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.admin-btn:hover {
  background: var(--float-bg);
}

.admin-btn.danger {
  color: #e5484d;
}

.admin-btn.danger:hover {
  background: color-mix(in srgb, #e5484d 12%, transparent);
}
</style>

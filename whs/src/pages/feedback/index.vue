<script setup>
/**
 * 反馈中心列表页（/feedback）。
 *
 * - 公开浏览反馈列表：分页 + 状态筛选 + 关键词搜索；
 * - 登录用户可点击「提交反馈」打开 Markdown 编辑器；
 * - 点击反馈卡片进入详情页 /feedback/:id。
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { MessageSquare, Plus, Search, UserRound, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import Top_navbar from '../../components/top_navbar.vue'
import Page_footer from '../../components/page_footer.vue'
import FeedbackEditor from '../../components/feedback_editor.vue'
import StatusDropdown from '../../components/status_dropdown.vue'
import { useAuth } from '../../composables/useAuth'
import { useTips } from '../../composables/useTips'

const { t } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()

const pageSize = 10
const items = ref([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref('')
const q = ref('')
const loading = ref(false)
const editorOpen = ref(false)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const isLoggedIn = computed(() => !!authState.token)

// 状态筛选选项（自定义下拉，保证与搜索框同款圆角/高度，且菜单不会溢出屏幕）
const statusOptions = computed(() => [
  { value: '', label: t('feedback.filterAll') },
  { value: 'pending', label: t('feedback.statusPending') },
  { value: 'resolved', label: t('feedback.statusResolved') },
  { value: 'closed', label: t('feedback.statusClosed') },
])

let searchTimer = null

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function categoryLabel(category) {
  const key = `feedback.category${category.charAt(0).toUpperCase()}${category.slice(1)}`
  return t(key)
}

function statusLabel(status) {
  const key = `feedback.status${status.charAt(0).toUpperCase()}${status.slice(1)}`
  return t(key)
}

async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      page_size: String(pageSize),
      status: statusFilter.value,
      q: q.value.trim(),
    })
    const res = await fetch(`/api/feedback?${params.toString()}`)
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      items.value = data.items || []
      total.value = data.total || 0
      // 当前页超出总页数时回退到最后一页
      if (page.value > totalPages.value && totalPages.value >= 1) {
        page.value = totalPages.value
        await fetchList()
      }
    } else {
      items.value = []
      total.value = 0
    }
  } catch (e) {
    items.value = []
    total.value = 0
    console.warn(e)
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  fetchList()
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(onFilterChange, 250)
}

function goDetail(id) {
  router.push(`/feedback/${id}`)
}

function openNew() {
  if (!isLoggedIn.value) {
    showTip('warning', t('feedback.loginToSubmit'))
    router.push('/login')
    return
  }
  editorOpen.value = true
}

function onSaved(data) {
  if (data && data.feedback_id) {
    router.push(`/feedback/${data.feedback_id}`)
    return
  }
  fetchList()
}

function goPage(target) {
  const next = Math.min(Math.max(1, target), totalPages.value)
  if (next === page.value) return
  page.value = next
  fetchList()
}

onMounted(() => {
  fetchList()
})

onUnmounted(() => {
  clearTimeout(searchTimer)
})
</script>

<template>
  <div class="fb-page">
    <Top_navbar />

    <main class="fb-main">
      <header class="fb-hero">
        <div class="fb-hero-text">
          <h1 class="fb-title">
            <MessageSquare :size="22" />
            {{ t('feedback.title') }}
          </h1>
          <p class="fb-subtitle">{{ t('feedback.subtitle') }}</p>
        </div>
        <button type="button" class="fb-new" @click="openNew">
          <Plus :size="18" />
          <span>{{ t('feedback.submit') }}</span>
        </button>
      </header>

      <!-- 工具栏：搜索 + 状态筛选（自定义下拉，与搜索框同款圆角/高度） -->
      <div class="fb-toolbar">
        <div class="fb-search">
          <Search :size="17" class="fb-search-icon" />
          <input
            v-model="q"
            type="text"
            class="fb-search-input"
            :placeholder="t('feedback.searchPlaceholder')"
            @input="onSearchInput"
            @keydown.enter="onFilterChange"
          />
        </div>
        <StatusDropdown
          v-model="statusFilter"
          :options="statusOptions"
          :aria-label="t('feedback.filterStatus')"
          @update:model-value="onFilterChange"
        />
      </div>

      <!-- 列表状态 -->
      <div v-if="loading" class="fb-state">
        <span class="spinner"></span>
      </div>
      <p v-else-if="!items.length" class="fb-state">
        {{ statusFilter || q.trim() ? t('feedback.emptyFiltered') : t('feedback.empty') }}
      </p>

      <ul v-else class="fb-list">
        <li
          v-for="item in items"
          :key="item.id"
          class="fb-card"
          role="button"
          tabindex="0"
          @click="goDetail(item.id)"
          @keydown.enter="goDetail(item.id)"
        >
          <div class="fb-card-head">
            <h2 class="fb-card-title">{{ item.title }}</h2>
            <span class="fb-status" :class="`is-${item.status}`">{{ statusLabel(item.status) }}</span>
          </div>
          <p class="fb-excerpt">{{ item.excerpt || t('feedback.excerptEmpty') }}</p>
          <div class="fb-meta">
            <span class="fb-badge">{{ categoryLabel(item.category) }}</span>
            <span class="fb-meta-item">
              <UserRound :size="14" />
              <RouterLink
                v-if="item.author_uid"
                :to="`/user/${item.author_uid}`"
                class="fb-author"
                @click.stop
              >{{ item.author_name || t('feedback.anonymous') }}</RouterLink>
              <span v-else class="fb-author">{{ item.author_name || t('feedback.anonymous') }}</span>
            </span>
            <span class="fb-meta-item">{{ formatTime(item.updated_at) }}</span>
            <span class="fb-meta-item fb-comments">
              <MessageSquare :size="14" />
              {{ item.comment_count || 0 }}
            </span>
          </div>
        </li>
      </ul>

      <!-- 分页 -->
      <nav v-if="totalPages > 1" class="fb-pagination">
        <button type="button" class="fb-page-btn" :disabled="page <= 1" @click="goPage(page - 1)">
          <ChevronLeft :size="16" />
          <span>{{ t('feedback.prev') }}</span>
        </button>
        <span class="fb-page-info">{{ t('feedback.page', { page, total: totalPages }) }}</span>
        <button type="button" class="fb-page-btn" :disabled="page >= totalPages" @click="goPage(page + 1)">
          <span>{{ t('feedback.next') }}</span>
          <ChevronRight :size="16" />
        </button>
      </nav>
    </main>

    <Page_footer />

    <FeedbackEditor
      :open="editorOpen"
      :feedback="null"
      @close="editorOpen = false"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.fb-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.fb-main {
  width: 100%;
  max-width: 900px;
  margin: 96px auto 0;
  padding: 0 16px 56px;
  flex: 1;
  box-sizing: border-box;
}

.fb-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.fb-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  color: var(--text-color);
}

.fb-subtitle {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--links-color);
}

.fb-new {
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

.fb-new:hover {
  background: #d99a1f;
  transform: translateY(-1px);
}

/* 加号图标：抵消全局 button > svg 的上移，使其视觉中心与文字对齐 */
.fb-new > svg {
  transform: translateY(0.9px);
}

.fb-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 18px;
}

.fb-search {
  flex: 1;
  min-width: 220px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border: 1px solid var(--float-bg);
  border-radius: 999px;
  background: var(--card-color);
}

.fb-search-icon {
  flex-shrink: 0;
  color: var(--links-color);
}

.fb-search-input {
  flex: 1;
  min-width: 0;
  padding: 12px 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 14px;
}

.fb-state {
  min-height: 30vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--links-color);
  font-size: 14px;
}

.spinner {
  width: 26px;
  height: 26px;
  border: 3px solid var(--float-bg);
  border-top-color: var(--notice-color);
  border-radius: 50%;
  animation: fb-spin 0.8s linear infinite;
}

@keyframes fb-spin {
  to {
    transform: rotate(360deg);
  }
}

.fb-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.fb-card {
  padding: 20px 22px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  background: var(--card-color);
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.fb-card:hover,
.fb-card:focus-visible {
  transform: translateY(-2px);
  border-color: var(--notice-color);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.12);
  outline: none;
}

.fb-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.fb-card-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.45;
  color: var(--text-color);
  word-break: break-word;
}

.fb-status {
  flex-shrink: 0;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.fb-status.is-pending {
  background: rgba(235, 170, 40, 0.16);
  color: #d99a1f;
}

.fb-status.is-resolved {
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
}

.fb-status.is-closed {
  background: rgba(148, 163, 184, 0.2);
  color: var(--links-color);
}

.fb-excerpt {
  margin: 10px 0 14px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--links-color);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.fb-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  font-size: 12.5px;
  color: var(--links-color);
}

.fb-badge {
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--float-bg);
  font-weight: 600;
}

.fb-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.fb-author {
  color: var(--links-color);
  text-decoration: none;
  transition: color 0.15s ease;
}

.fb-author:hover {
  color: var(--text-color);
}

.fb-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 26px;
}

.fb-page-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.fb-page-btn:hover:not(:disabled) {
  color: var(--text-color);
  background: var(--float-bg);
}

.fb-page-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.fb-page-info {
  font-size: 13px;
  color: var(--links-color);
}

@media (max-width: 768px) {
  .fb-main {
    margin-top: 84px;
    padding: 0 14px 40px;
  }

  .fb-hero {
    align-items: flex-start;
  }

  .fb-title {
    font-size: 21px;
  }

  .fb-new {
    width: 100%;
    justify-content: center;
  }

  .fb-search {
    min-width: 0;
    width: 100%;
  }

  .fb-card {
    padding: 16px;
  }
}
</style>

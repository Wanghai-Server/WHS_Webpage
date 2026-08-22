<script setup>
/**
 * 维基搜索框：防抖实时搜索（按当前语言向后端请求），下拉展示结果。
 * 语言切换时自动用新语言重新搜索。
 */
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search, CornerDownLeft, ChevronRight } from 'lucide-vue-next'
import { wikiApi } from '../../composables/wiki/api.js'
import { useWikiLocale } from '../../composables/wiki/locale.js'

const props = defineProps({
  size: { type: String, default: 'normal' }, // 'normal' | 'large'
})

const { t } = useI18n()
const { lang } = useWikiLocale()
const router = useRouter()

const query = ref('')
const results = ref([])
const open = ref(false)
const loading = ref(false)
const searched = ref(false)
let timer = null
let seq = 0

async function runSearch() {
  const q = query.value.trim()
  if (!q) {
    results.value = []
    open.value = false
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
    open.value = true
  } catch {
    if (current !== seq) return
    results.value = []
    searched.value = true
    open.value = true
  } finally {
    if (current === seq) loading.value = false
  }
}

function onInput() {
  clearTimeout(timer)
  timer = setTimeout(runSearch, 250)
}

// 精确标题命中：当前语言下某页面标题与关键词完全一致（忽略大小写与首尾空格）
const exactResult = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return null
  return (
    results.value.find(
      (r) => String(r.title || '').trim().toLowerCase() === q
    ) || null
  )
})

// 回车：精确标题命中 -> 直接打开该页；否则 -> 跳转 /wiki/search 展示全部结果
function openFirst() {
  if (exactResult.value) {
    go(exactResult.value)
  } else if (query.value.trim()) {
    showAllResults()
  }
}

function showAllResults() {
  open.value = false
  router.push({ path: '/wiki/search', query: { q: query.value.trim() } })
}

function go(item) {
  open.value = false
  query.value = ''
  results.value = []
  searched.value = false
  router.push(`/wiki/page/${item.slug}`)
}

function onKeydown(e) {
  if (e.key === 'Enter' && open.value) {
    e.preventDefault()
    openFirst()
  } else if (e.key === 'Escape') {
    open.value = false
  }
}

// 语言切换：用新语言重新搜索
watch(lang, () => {
  if (query.value.trim()) runSearch()
})

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="wiki-search" :class="`is-${size}`">
    <div class="search-box">
      <Search :size="size === 'large' ? 22 : 16" class="search-icon" />
      <input
        v-model="query"
        type="text"
        class="search-input"
        :placeholder="t('pages.wiki.search.placeholder')"
        @input="onInput"
        @focus="open = !!query.trim()"
        @keydown="onKeydown"
        @blur="setTimeout(() => (open = false), 150)"
      />
      <CornerDownLeft v-if="results.length" :size="size === 'large' ? 18 : 14" class="enter-icon" />
      <span v-else-if="loading" class="search-spinner"></span>
    </div>

    <Transition name="search-drop">
      <!-- 未键入内容时不展示下拉（避免聚焦时出现空提示框） -->
      <div v-if="open && query.trim()" class="search-drop">
        <p v-if="loading" class="drop-tip">{{ t('pages.wiki.search.hint') }}</p>
        <p v-else-if="searched && !results.length" class="drop-tip">
          {{ t('pages.wiki.search.noResults') }}
        </p>
        <ul v-else-if="results.length" class="drop-list">
          <li v-for="item in results" :key="item.slug">
            <button type="button" class="drop-item" @mousedown.prevent="go(item)">
              <span class="drop-title">{{ item.title || item.slug }}</span>
              <span class="drop-snippet">{{ item.snippet }}</span>
            </button>
          </li>
        </ul>

        <!-- 查看全部结果（回车无精确标题命中时同样跳转至此） -->
        <div v-if="results.length" class="drop-footer">
          <button type="button" class="drop-all" @mousedown.prevent="showAllResults">
            {{ t('pages.wiki.search.allResults') }}
            <ChevronRight :size="14" />
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.wiki-search {
  position: relative;
}

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
  margin-left: 16px;
}

.search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-color);
  font-size: 14px;
  padding: 10px 0;
}

.is-large .search-input {
  font-size: 17px;
  padding: 14px 0;
}

.enter-icon {
  flex-shrink: 0;
  color: var(--links-color);
  margin-right: 16px;
  opacity: 0.8;
}

.search-spinner {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  margin-right: 16px;
  border: 2px solid var(--links-color);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spinner-rotate 0.7s linear infinite;
}

@keyframes spinner-rotate {
  to {
    transform: rotate(360deg);
  }
}

/* 下拉 */
.search-drop {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 40;
  max-height: 340px;
  overflow-y: auto;
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14);
  padding: 6px;
}

.drop-tip {
  margin: 0;
  padding: 12px 14px;
  font-size: 13px;
  color: var(--links-color);
}

.drop-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.drop-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  box-sizing: border-box;
  padding: 9px 12px;
  border: none;
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.drop-item:hover {
  background: var(--float-bg);
}

/* 查看全部结果 */
.drop-footer {
  padding: 4px 6px;
  border-top: 1px solid var(--float-bg);
  margin-top: 4px;
}

.drop-all {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  box-sizing: border-box;
  padding: 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.drop-all:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.drop-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drop-snippet {
  font-size: 12.5px;
  color: var(--links-color);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 下拉动画 */
.search-drop-enter-active,
.search-drop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.search-drop-enter-from,
.search-drop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>

<script setup>
/**
 * 顶部导航全量搜索：点击搜索图标展开建议面板。
 *
 * - 输入防抖调用 /api/search（wiki 页面 + 用户），分组展示建议；
 * - 回车/点击：wiki 标题、用户 username / player_name / uid 精确命中则直接打开，
 *   否则跳转 /search?q= 展示全部结果。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search, ChevronRight } from 'lucide-vue-next'
import { useWikiLocale } from '../composables/wiki/locale.js'

const { t } = useI18n()
const { lang } = useWikiLocale()
const router = useRouter()

const open = ref(false)
const query = ref('')
const results = ref({ wiki: [], users: [] })
const loading = ref(false)
let timer = null
let seq = 0

async function runSearch() {
  const q = query.value.trim()
  if (!q) {
    results.value = { wiki: [], users: [] }
    return
  }
  const current = ++seq
  loading.value = true
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&lang=${lang.value}`)
    const data = await res.json().catch(() => null)
    if (current !== seq) return
    results.value = {
      wiki: (data && data.wiki) || [],
      users: (data && data.users) || [],
    }
  } catch {
    if (current !== seq) return
    results.value = { wiki: [], users: [] }
  } finally {
    if (current === seq) loading.value = false
  }
}

function onInput() {
  clearTimeout(timer)
  timer = setTimeout(runSearch, 250)
}

// 精确命中：wiki 标题完全相等，或用户 username / player_name / uid 完全相等
const exactMatch = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return null
  const page = results.value.wiki.find(
    (r) => String(r.title || '').trim().toLowerCase() === q
  )
  if (page) return { kind: 'page', item: page }
  const user = results.value.users.find(
    (u) =>
      String(u.username || '').trim().toLowerCase() === q ||
      String(u.player_name || '').trim().toLowerCase() === q ||
      String(u.uid) === query.value.trim()
  )
  if (user) return { kind: 'user', item: user }
  return null
})

function openTarget(match) {
  open.value = false
  if (match.kind === 'page') router.push(`/wiki/page/${match.item.slug}`)
  else router.push(`/user/${match.item.uid}`)
}

// 回车：精确命中直接打开；否则跳转 /search
function onSubmit() {
  if (exactMatch.value) openTarget(exactMatch.value)
  else if (query.value.trim()) goFull()
}

function goFull() {
  open.value = false
  router.push({ path: '/search', query: { q: query.value.trim() } })
}

function goPage(page) {
  open.value = false
  router.push(`/wiki/page/${page.slug}`)
}

function goUser(user) {
  open.value = false
  router.push(`/user/${user.uid}`)
}

function onKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault()
    onSubmit()
  } else if (e.key === 'Escape') {
    open.value = false
  }
}

// 点击外部关闭
function onDocClick(e) {
  if (open.value && !(e.target.closest && e.target.closest('.global-search'))) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  clearTimeout(timer)
})

// 语言切换：重新搜索
watch(lang, () => {
  if (query.value.trim()) runSearch()
})
</script>

<template>
  <div class="global-search">
    <button
      type="button"
      class="gs-toggle"
      :class="{ active: open }"
      :aria-label="t('search.title')"
      :title="t('search.title')"
      @click="open = !open"
    >
      <Search :size="17" />
    </button>

    <Transition name="gs-drop">
      <div v-if="open" class="gs-panel">
        <!-- 输入框 -->
        <div class="gs-box">
          <Search :size="15" class="gs-box-icon" />
          <input
            v-model="query"
            type="text"
            class="gs-input"
            :placeholder="t('search.placeholder')"
            autofocus
            @input="onInput"
            @keydown="onKeydown"
          />
          <span v-if="loading" class="gs-spinner"></span>
        </div>

        <!-- 建议列表 -->
        <div v-if="query.trim()" class="gs-body">
          <p v-if="loading" class="gs-tip">{{ t('search.loading') }}</p>
          <p v-else-if="!results.wiki.length && !results.users.length" class="gs-tip">
            {{ t('search.noResults') }}
          </p>
          <template v-else>
            <p v-if="results.wiki.length" class="gs-group">{{ t('search.wikiLabel') }}</p>
            <ul v-if="results.wiki.length" class="gs-list">
              <li v-for="page in results.wiki.slice(0, 5)" :key="'w' + page.slug">
                <button type="button" class="gs-item" @mousedown.prevent="goPage(page)">
                  <span class="gs-item-title">{{ page.title || page.slug }}</span>
                  <span class="gs-item-sub">{{ page.slug }}</span>
                </button>
              </li>
            </ul>

            <p v-if="results.users.length" class="gs-group">{{ t('search.usersLabel') }}</p>
            <ul v-if="results.users.length" class="gs-list">
              <li v-for="user in results.users.slice(0, 3)" :key="'u' + user.uid">
                <button type="button" class="gs-item" @mousedown.prevent="goUser(user)">
                  <span class="gs-item-title">{{ user.username }}</span>
                  <span class="gs-item-sub">
                    {{ user.fullname || '' }}{{ user.player_name ? ` · ${user.player_name}` : '' }}
                  </span>
                </button>
              </li>
            </ul>
          </template>
        </div>

        <!-- 查看全部结果 -->
        <button
          v-if="query.trim() && (results.wiki.length || results.users.length)"
          type="button"
          class="gs-all"
          @mousedown.prevent="goFull"
        >
          {{ t('search.allResults') }}
          <ChevronRight :size="14" />
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.global-search {
  position: relative;
  display: flex;
  align-items: center;
}

.gs-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-left: 10px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.gs-toggle:hover,
.gs-toggle.active {
  background: var(--float-bg);
}

/* 面板 */
.gs-panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 3000;
  width: 340px;
  max-width: 88vw;
  padding: 10px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 16px;
  background: var(--navbar-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14);
}

.gs-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--float-bg);
  border-radius: 999px;
  background: var(--card-color);
}

.gs-box:focus-within {
  border-color: var(--notice-color);
}

.gs-box-icon {
  flex-shrink: 0;
  color: var(--links-color);
}

.gs-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-color);
  font-size: 14px;
}

.gs-spinner {
  flex-shrink: 0;
  width: 13px;
  height: 13px;
  border: 2px solid var(--links-color);
  border-top-color: transparent;
  border-radius: 50%;
  animation: gs-rotate 0.7s linear infinite;
}

@keyframes gs-rotate {
  to {
    transform: rotate(360deg);
  }
}

.gs-body {
  margin-top: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.gs-tip {
  margin: 0;
  padding: 12px 10px;
  font-size: 13px;
  color: var(--links-color);
  text-align: center;
}

.gs-group {
  margin: 8px 10px 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--links-color);
}

.gs-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.gs-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  box-sizing: border-box;
  padding: 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.gs-item:hover {
  background: var(--float-bg);
}

.gs-item-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gs-item-sub {
  font-size: 12px;
  color: var(--links-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gs-all {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  box-sizing: border-box;
  margin-top: 6px;
  padding: 8px 10px;
  border: none;
  border-top: 1px solid var(--float-bg);
  background: transparent;
  color: var(--links-color);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.12s ease, background-color 0.12s ease;
}

.gs-all:hover {
  color: var(--text-color);
  background: var(--float-bg);
  border-radius: 0 0 10px 10px;
}

/* 面板动画 */
.gs-drop-enter-active,
.gs-drop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.gs-drop-enter-from,
.gs-drop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* 移动端隐藏（导航栏无空间） */
@media (max-width: 768px) {
  .global-search {
    display: none;
  }
}
</style>

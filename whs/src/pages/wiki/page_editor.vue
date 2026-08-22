<script setup>
/**
 * 维基编辑器：双栏（源码 + 实时预览）。
 *
 * - 编辑语言跟随站点语言（底部导航栏切换）；各语言内容独立加载与保存；
 * - 新页面可输入 slug；编辑页可改 slug（保存 = 新建新路径 + 删除原路径，双语言一并迁移）；
 * - 乐观锁：保存携带 base_rev，409 冲突时弹窗选择"加载最新"或"强制保存"；
 * - 未保存修改：路由离开确认 + beforeunload 守卫。
 */
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft, Save, Undo2, Bold, Italic, Code, SquareCode, Link as LinkIcon,
  Image, Quote, List, ListOrdered, ListTodo, Table, Minus, Upload,
  AlertTriangle, GripVertical, GripHorizontal, ChevronDown, Strikethrough,
} from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'
import { useDialogBox } from '../../composables/useDialogBox'
import { wikiApi, WikiApiError } from '../../composables/wiki/api.js'
import { useWikiLocale } from '../../composables/wiki/locale.js'
import WikiMarkdown from '../../components/wiki/wiki_markdown.vue'

const { t } = useI18n()
const { lang } = useWikiLocale()
const route = useRoute()
const router = useRouter()
const { state: authState } = useAuth()
const dialogBox = useDialogBox()

// 统一的"未保存修改"确认框
function confirmLeave() {
  return dialogBox.confirm({
    title: t('pages.wiki.editor.dirty'),
    message: t('pages.wiki.editor.confirmLeave'),
  })
}

// 统一的保存失败提示框
function showSaveError(err) {
  return dialogBox.alert({
    title: t('pages.wiki.editor.saveFailed'),
    message: String((err && err.message) || t('pages.wiki.loadError')),
  })
}

const paramSlug = computed(() => String(route.params.slug || ''))
const querySlug = computed(() => String(route.query.slug || ''))
const isNew = computed(() => !paramSlug.value)
const originalSlug = computed(() => paramSlug.value)

const myPermission = computed(() =>
  authState.user ? authState.user.permission || 0 : 0
)
// 权限门：新建页面按默认 2 校验；编辑页面按该页 min_permission 校验
const denied = ref(false)
const minPermission = ref(2)

const slug = ref(isNew.value ? querySlug.value : paramSlug.value)
const text = ref('')
const summary = ref('')
// 消歧义页标记（保存时随内容提交）
const disambig = ref(false)
// 编辑语言跟随站点语言（底部导航栏切换），不提供页内切换器
const saving = ref(false)
const savedFlash = ref(false)
const slugError = ref('')

// 各语言的内容与修订号（懒加载）
const loaded = reactive({ zh: false, en: false })
const originals = reactive({ zh: '', en: '' })
const revNos = reactive({ zh: 0, en: 0 })

const dirty = computed(() => text.value !== originals[lang.value])
const previewText = ref('')

const conflict = ref(false)
let conflictNewRev = 0

const SLUG_RE = /^[a-z0-9-]+(?:\/[a-z0-9-]+)*$/

// ---------------- 数据加载 ----------------

async function loadLang(l) {
  if (loaded[l] || isNew.value) return
  try {
    const data = await wikiApi.getPage(originalSlug.value, l)
    if (data.redirect) {
      // 旧路径已有重定向：直接跳转到新路径的编辑器
      router.replace(`/wiki/edit/${data.redirect}`)
      return
    }
    minPermission.value = data.page.min_permission || 2
    if (myPermission.value < minPermission.value) {
      denied.value = true
      return
    }
    loaded[l] = true
    originals[l] = data.page.content || ''
    revNos[l] = data.page.rev_no || 0
    if (l === lang.value) {
      disambig.value = !!data.page.disambig
      text.value = originals[l]
      previewText.value = originals[l]
      undoStack.value = [] // 内容整体替换，清空撤销历史
      markEditorStable()
    }
  } catch (err) {
    if (err instanceof WikiApiError && err.code === 'wiki_page_not_found') {
      // 页面不存在（直接访问 /wiki/edit/xxx）：进入新建模式
      loaded[l] = true
      originals[l] = ''
    }
  }
}

// 站点语言切换：加载对应语言的内容（未保存修改需确认）
watch(lang, async (v) => {
  if (dirty.value && !(await confirmLeave())) return
  if (!loaded[v]) {
    await loadLang(v)
  } else {
    text.value = originals[v]
    previewText.value = originals[v]
    undoStack.value = []
    markEditorStable()
  }
})

onMounted(() => {
  if (isNew.value && myPermission.value < 2) {
    denied.value = true
  } else {
    loadLang(lang.value)
  }
  window.addEventListener('beforeunload', handleBeforeUnload)
  document.addEventListener('click', onToolbarDocClick)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  document.removeEventListener('click', onToolbarDocClick)
  // 拖拽中途卸载时清理监听与全局样式
  dragging.value = false
  draggingH.value = false
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('pointermove', onDividerPointerMove)
  window.removeEventListener('pointerup', onDividerPointerUp)
  window.removeEventListener('pointermove', onHeightPointerMove)
  window.removeEventListener('pointerup', onHeightPointerUp)
})

function handleBeforeUnload(e) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  // vue-router 支持返回 Promise：对话框确认后决定是否离开
  return confirmLeave()
})

// ---------------- 撤销 ----------------

// 撤销栈：记录每次语法插入/编辑/键入前的快照（上限 50 条）
const undoStack = ref([])
function pushUndo() {
  undoStack.value.push(text.value)
  if (undoStack.value.length > 50) undoStack.value.shift()
}

function undo() {
  if (!undoStack.value.length || saving.value) return
  const ta = taRef.value
  const scrollTop = ta ? ta.scrollTop : 0
  text.value = undoStack.value.pop()
  markEditorStable()
  if (ta) {
    requestAnimationFrame(() => {
      ta.scrollTop = scrollTop
    })
  }
}

// 键入跟踪：连续输入合并为一个撤销步骤（快照为"键入前"的值）
let typingBurst = false
let lastInputValue = ''
function onTextareaInput(e) {
  const current = String(e.target ? e.target.value : text.value)
  if (current === lastInputValue) return
  if (!typingBurst) {
    undoStack.value.push(lastInputValue)
    if (undoStack.value.length > 50) undoStack.value.shift()
    typingBurst = true
  }
  lastInputValue = current
}

// 非键入变更（工具条插入 / 撤销 / 加载）后标记编辑器稳定，结束键入突发
function markEditorStable() {
  typingBurst = false
  lastInputValue = text.value
}

function wrapSelection(before, after, placeholder) {
  const ta = taRef.value
  if (!ta) return
  pushUndo()
  const scrollTop = ta.scrollTop
  const { selectionStart: s, selectionEnd: e } = ta
  const selected = text.value.slice(s, e) || placeholder || ''
  text.value = text.value.slice(0, s) + before + selected + after + text.value.slice(e)
  markEditorStable()
  requestAnimationFrame(() => {
    ta.focus()
    ta.setSelectionRange(s + before.length, s + before.length + selected.length)
    // 程序化改值会重置滚动位置：DOM 更新后恢复，避免跳回顶部
    ta.scrollTop = scrollTop
  })
}

function insertLine(line, extraNewline = true) {
  const ta = taRef.value
  if (!ta) return
  pushUndo()
  const scrollTop = ta.scrollTop
  const s = ta.selectionStart
  const before = text.value.slice(0, s)
  const nl = before.length && !before.endsWith('\n') ? '\n' : ''
  const suffix = extraNewline ? '\n' : ''
  text.value = before + nl + line + suffix + text.value.slice(s)
  markEditorStable()
  requestAnimationFrame(() => {
    ta.focus()
    ta.setSelectionRange(s + nl.length + line.length, s + nl.length + line.length)
    ta.scrollTop = scrollTop
  })
}

const taRef = ref(null)

function insertLink() {
  const ta = taRef.value
  if (!ta) return
  const scrollTop = ta.scrollTop
  const s = ta.selectionStart
  const e = ta.selectionEnd
  pushUndo()
  const sel = text.value.slice(s, e)
  const markdown = sel ? `[${sel}](https://)` : '[链接](https://)'
  text.value = text.value.slice(0, s) + markdown + text.value.slice(e)
  markEditorStable()
  requestAnimationFrame(() => {
    ta.focus()
    ta.setSelectionRange(s, s + markdown.length)
    ta.scrollTop = scrollTop
  })
}

function insertImage() {
  const ta = taRef.value
  if (!ta) return
  const scrollTop = ta.scrollTop
  const s = ta.selectionStart
  const e = ta.selectionEnd
  pushUndo()
  const sel = text.value.slice(s, e)
  const markdown = sel ? `![${sel}](https://)` : '![图片描述](https://)'
  text.value = text.value.slice(0, s) + markdown + text.value.slice(e)
  markEditorStable()
  requestAnimationFrame(() => {
    ta.focus()
    ta.setSelectionRange(s, s + markdown.length)
    ta.scrollTop = scrollTop
  })
}

function insertTable() {
  insertLine('| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n|  |  |  |', false)
}

// H 下拉：H1-H6 标题
const headingsOpen = ref(false)
function toggleHeadings() {
  headingsOpen.value = !headingsOpen.value
}
function insertHeading(n) {
  headingsOpen.value = false
  insertLine('#'.repeat(n) + ' ')
}
// 点击工具条外部时关闭 H 下拉
function onToolbarDocClick(e) {
  if (headingsOpen.value && !(e.target.closest && e.target.closest('.tool-dd'))) {
    headingsOpen.value = false
  }
}

// ---------------- 媒体上传 ----------------

const fileInputRef = ref(null)
const uploading = ref(false)

// 在光标处插入一段 Markdown（用于上传结果）
function insertMarkdownAtCursor(markdown) {
  const ta = taRef.value
  if (!ta) return
  const scrollTop = ta.scrollTop
  const s = ta.selectionStart
  const e = ta.selectionEnd
  pushUndo()
  text.value = text.value.slice(0, s) + markdown + text.value.slice(e)
  markEditorStable()
  requestAnimationFrame(() => {
    ta.focus()
    ta.setSelectionRange(s + markdown.length, s + markdown.length)
    ta.scrollTop = scrollTop
  })
}

async function onFileChange(e) {
  const file = e.target.files && e.target.files[0]
  e.target.value = '' // 允许重复选择同一文件
  if (!file || uploading.value) return
  uploading.value = true
  try {
    const data = await wikiApi.upload(file)
    if (!data || !data.url) throw new Error(t('pages.wiki.loadError'))
    const snippet =
      data.type === 'image'
        ? `![图片描述](${data.url})`
        : data.type === 'video'
          ? `![视频](${data.url})`
          : `![音频](${data.url})`
    insertMarkdownAtCursor(snippet)
  } catch (err) {
    await showSaveError(err)
  } finally {
    uploading.value = false
  }
}

// ---------------- 双栏拖拽调整大小 ----------------

// 源码栏占比（%），持久化到 localStorage
const split = ref(
  Math.min(80, Math.max(20, Number(localStorage.getItem('wiki.editor.split')) || 50))
)
watch(split, (v) => localStorage.setItem('wiki.editor.split', String(v)))

const panesRef = ref(null)
const dragging = ref(false)
let dragStartX = 0
let dragStartSplit = 50

function onDividerPointerDown(e) {
  dragging.value = true
  dragStartX = e.clientX
  dragStartSplit = split.value
  e.preventDefault()
  // 拖拽期间全局禁止选中文本，光标统一为 col-resize
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  window.addEventListener('pointermove', onDividerPointerMove)
  window.addEventListener('pointerup', onDividerPointerUp)
}

function onDividerPointerMove(e) {
  if (!dragging.value || !panesRef.value) return
  const rect = panesRef.value.getBoundingClientRect()
  if (rect.width <= 0) return
  const delta = e.clientX - dragStartX
  split.value = Math.min(80, Math.max(20, dragStartSplit + (delta / rect.width) * 100))
}

function onDividerPointerUp() {
  dragging.value = false
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('pointermove', onDividerPointerMove)
  window.removeEventListener('pointerup', onDividerPointerUp)
}

// ---------------- 底部拖拽：调整双栏整体高度 ----------------

// 超出默认高度的增量（px），持久化到 localStorage；最小即默认高度
const extraH = ref(
  Math.min(1000, Math.max(0, Number(localStorage.getItem('wiki.editor.extraH')) || 0))
)
watch(extraH, (v) => localStorage.setItem('wiki.editor.extraH', String(v)))

const draggingH = ref(false)
let dragStartY = 0
let dragStartExtra = 0

function onHeightPointerDown(e) {
  draggingH.value = true
  dragStartY = e.clientY
  dragStartExtra = extraH.value
  e.preventDefault()
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'row-resize'
  window.addEventListener('pointermove', onHeightPointerMove)
  window.addEventListener('pointerup', onHeightPointerUp)
}

function onHeightPointerMove(e) {
  if (!draggingH.value) return
  // 只能拉长（≥0），上限 1000px，避免拖出不可控高度
  extraH.value = Math.max(0, Math.min(1000, dragStartExtra + (e.clientY - dragStartY)))
}

function onHeightPointerUp() {
  draggingH.value = false
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('pointermove', onHeightPointerMove)
  window.removeEventListener('pointerup', onHeightPointerUp)
}

// ---------------- 预览 ----------------

let previewTimer = null
watch(text, () => {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(() => {
    // 预览内容整体替换会重置滚动位置：更新前快照，重渲染后恢复
    const pv = previewRef.value
    const scrollTop = pv ? pv.scrollTop : 0
    previewText.value = text.value
    if (pv) {
      requestAnimationFrame(() => {
        if (previewRef.value) previewRef.value.scrollTop = scrollTop
      })
    }
  }, 120)
})

// 源码滚动 -> 预览同步滚动
function syncScroll() {
  const src = taRef.value
  const dst = previewRef.value
  if (!src || !dst) return
  const ratio = src.scrollTop / Math.max(1, src.scrollHeight - src.clientHeight)
  dst.scrollTop = ratio * Math.max(0, dst.scrollHeight - dst.clientHeight)
}

const previewRef = ref(null)

// ---------------- 校验与保存 ----------------

function validate() {
  slugError.value = ''
  const s = slug.value.trim()
  if (!s) {
    slugError.value = t('pages.wiki.editor.slugHint')
    return false
  }
  if (!SLUG_RE.test(s) || s.length > 200) {
    slugError.value = t('pages.wiki.editor.slugHint')
    return false
  }
  slug.value = s
  return true
}

async function save() {
  if (saving.value) return
  if (denied.value) return
  if (!validate()) return
  const content = text.value.trim()
  if (!content) return
  saving.value = true
  try {
    if (isNew.value) {
      await wikiApi.createPage(slug.value, content, lang.value, disambig.value)
      // 标记已保存（新建模式 originals 原本为空，不更新会导致离开守卫误报"未保存"）
      originals[lang.value] = text.value
      undoStack.value = []
      router.push(`/wiki/page/${slug.value}`)
      return
    }
    if (slug.value === originalSlug.value) {
      const data = await wikiApi.updatePage(
        slug.value, content, lang.value, revNos[lang.value], summary.value.trim() || null, disambig.value
      )
      revNos[lang.value] = data.page.rev_no
      originals[lang.value] = text.value
      undoStack.value = []
      flashSaved()
      router.push(`/wiki/page/${slug.value}`)
      return
    }
    // 改名：先建新路径（迁移双语言），再删旧路径
    await renamePage(content)
  } catch (err) {
    if (err instanceof WikiApiError && err.code === 'wiki_revision_conflict') {
      conflict.value = true
      conflictNewRev = 0
      try {
        const latest = await wikiApi.getPage(slug.value, lang.value)
        conflictNewRev = latest.page.rev_no
      } catch {
        /* 忽略 */
      }
      return
    }
    if (err instanceof WikiApiError && err.code === 'wiki_slug_exists') {
      slugError.value = String(err.message)
      return
    }
    await showSaveError(err)
  } finally {
    saving.value = false
  }
}

async function forceSave() {
  conflict.value = false
  saving.value = true
  try {
    revNos[lang.value] = conflictNewRev
    await wikiApi.updatePage(
      slug.value, text.value.trim(), lang.value,
      revNos[lang.value], summary.value.trim() || null, disambig.value
    )
    originals[lang.value] = text.value
    undoStack.value = []
    router.push(`/wiki/page/${slug.value}`)
  } catch (err) {
    await showSaveError(err)
  } finally {
    saving.value = false
  }
}

async function loadLatest() {
  conflict.value = false
  const l = lang.value
  try {
    const data = await wikiApi.getPage(slug.value, l)
    if (data.redirect) {
      router.replace(`/wiki/edit/${data.redirect}`)
      return
    }
    loaded[l] = true
    originals[l] = data.page.content || ''
    revNos[l] = data.page.rev_no || 0
    disambig.value = !!data.page.disambig
    text.value = originals[l]
    previewText.value = originals[l]
    undoStack.value = []
    markEditorStable()
  } catch {
    /* 忽略 */
  }
}

// 改名保存：双语言一并迁移
async function renamePage(currentContent) {
  const other = lang.value === 'en' ? 'zh' : 'en'
  if (!loaded[other]) await loadLang(other)
  const otherContent = originals[other]

  // 1) 在新路径下创建当前语言（若新路径已存在则报错）
  await wikiApi.createPage(slug.value, currentContent, lang.value, disambig.value)
  // 2) 迁移另一语言（新页面该语言尚无修订，base_rev=0）
  if (otherContent && otherContent.trim()) {
    await wikiApi.updatePage(slug.value, otherContent, other, 0, null, disambig.value)
  }
  // 3) 删除旧路径（若因存在子页面失败，则保留旧页，提示用户）
  try {
    await wikiApi.deletePage(originalSlug.value)
  } catch (err) {
    await showSaveError(err)
  }
  // 4) 旧路径 -> 新路径重定向（旧链接自动跳转；删除失败时来源仍是页面会被拒绝）
  try {
    await wikiApi.createRedirect(originalSlug.value, slug.value)
  } catch (err) {
    await showSaveError(err)
  }
  originals[lang.value] = text.value
  undoStack.value = []
  router.push(`/wiki/page/${slug.value}`)
}

function flashSaved() {
  savedFlash.value = true
  setTimeout(() => (savedFlash.value = false), 1500)
}

function back() {
  // 不再自行确认：由 onBeforeRouteLeave 守卫统一弹出一次"未保存修改"确认
  if (originalSlug.value) router.push(`/wiki/page/${originalSlug.value}`)
  else router.push('/wiki')
}

// ---------------- 字符统计 ----------------

const charCount = computed(() => text.value.replace(/\s/g, '').length)
</script>

<template>
  <div v-if="denied" class="no-perm">
    <p>{{ t('pages.wiki.permission.notEnough') }}</p>
  </div>

  <div v-else class="editor">
    <!-- 顶部栏 -->
    <header class="editor-top">
      <button type="button" class="top-btn" @click="back">
        <ArrowLeft :size="17" />
      </button>

      <input
        v-model="slug"
        type="text"
        class="slug-input"
        :class="{ error: slugError }"
        :placeholder="t('pages.wiki.editor.slugPlaceholder')"
      />
      <span v-if="slugError" class="slug-error">{{ slugError }}</span>
      <span v-else-if="!isNew && slug !== originalSlug" class="slug-warn">
        {{ t('pages.wiki.editor.renameWarning') }}
      </span>

      <span v-if="savedFlash" class="saved-tag">{{ t('pages.wiki.editor.saved') }}</span>
      <span v-else-if="dirty" class="dirty-tag">{{ t('pages.wiki.editor.dirty') }}</span>

      <div class="top-actions">
        <button
          type="button"
          class="undo-btn"
          :disabled="!undoStack.length || saving"
          :title="t('pages.wiki.editor.undo')"
          @click="undo"
        >
          <Undo2 :size="15" />
          {{ t('pages.wiki.editor.undo') }}
        </button>
        <button type="button" class="save-btn" :disabled="saving" @click="save">
          <Save :size="15" />
          {{ saving ? t('pages.wiki.editor.saving') : t('pages.wiki.actions.save') }}
        </button>
      </div>
    </header>

    <!-- 编辑摘要（位于保存按钮可见处之下、语法工具条之上）+ 消歧义标记 -->
    <div class="summary-row">
      <input
        v-model="summary"
        type="text"
        class="summary-input"
        :placeholder="t('pages.wiki.editor.summary')"
      />
      <label class="disambig-check">
        <input v-model="disambig" type="checkbox" />
        {{ t('pages.wiki.editor.disambig') }}
      </label>
    </div>

    <!-- 工具条：Markdown 语法提示（H 下拉 H1-H6 + 全量语法） -->
    <div class="toolbar">
      <!-- H1-H6 下拉 -->
      <div class="tool-dd">
        <button
          type="button"
          class="tool-btn dd-trigger"
          :class="{ active: headingsOpen }"
          title="H"
          @click="toggleHeadings"
        >
          <span class="tool-h">H</span>
          <ChevronDown :size="12" />
        </button>
        <Transition name="dd">
          <div v-if="headingsOpen" class="dd-menu">
            <button
              v-for="n in 6"
              :key="n"
              type="button"
              class="dd-item"
              @click="insertHeading(n)"
            >
              <span class="dd-h" :class="`is-h${n}`">H{{ n }}</span>
            </button>
          </div>
        </Transition>
      </div>

      <span class="tool-sep"></span>

      <button type="button" class="tool-btn" title="**" @click="wrapSelection('**', '**', '加粗')">
        <Bold :size="15" />
      </button>
      <button type="button" class="tool-btn" title="*" @click="wrapSelection('*', '*', '斜体')">
        <i class="tool-italic">I</i>
      </button>
      <button type="button" class="tool-btn" title="~~" @click="wrapSelection('~~', '~~', '删除线')">
        <Strikethrough :size="15" />
      </button>
      <button type="button" class="tool-btn" title="`" @click="wrapSelection('`', '`', 'code')">
        <Code :size="15" />
      </button>
      <button type="button" class="tool-btn" title="```" @click="wrapSelection('```\n', '\n```', '代码')">
        <SquareCode :size="15" />
      </button>

      <span class="tool-sep"></span>

      <button type="button" class="tool-btn" title="link" @click="insertLink">
        <LinkIcon :size="15" />
      </button>
      <button type="button" class="tool-btn" title="image" @click="insertImage">
        <Image :size="15" />
      </button>
      <button type="button" class="tool-btn" title="quote" @click="insertLine('> ')">
        <Quote :size="15" />
      </button>
      <button type="button" class="tool-btn" title="list" @click="insertLine('- ')">
        <List :size="15" />
      </button>
      <button type="button" class="tool-btn" title="1." @click="insertLine('1. ')">
        <ListOrdered :size="15" />
      </button>
      <button type="button" class="tool-btn" title="- [ ]" @click="insertLine('- [ ] ')">
        <ListTodo :size="15" />
      </button>
      <button type="button" class="tool-btn" title="table" @click="insertTable">
        <Table :size="15" />
      </button>
      <button type="button" class="tool-btn" title="---" @click="insertLine('---', false)">
        <Minus :size="15" />
      </button>

      <span class="tool-sep"></span>

      <!-- 上传图片 / 视频 / 音频 -->
      <input
        ref="fileInputRef"
        type="file"
        class="file-input"
        accept=".png,.jpg,.jpeg,.webp,.gif,.mp4,.webm,.mov,.mp3,.wav,.ogg,.m4a,.aac,.flac"
        @change="onFileChange"
      />
      <button
        type="button"
        class="tool-btn"
        :disabled="uploading"
        :title="uploading ? t('pages.wiki.editor.uploading') : t('pages.wiki.editor.upload')"
        @click="fileInputRef?.click()"
      >
        <Upload :size="15" />
      </button>

      <span class="tool-spacer"></span>
      <span class="char-count">{{ charCount }} {{ t('pages.wiki.editor.chars') }}</span>
    </div>

    <!-- 双栏（中间分隔条可拖拽调整左右大小；底部拖拽条可拉长高度） -->
    <div
      ref="panesRef"
      class="panes"
      :class="{ dragging }"
      :style="{ '--source-w': split + '%', '--extra-h': extraH + 'px' }"
    >
      <div class="pane pane-source">
        <textarea
          ref="taRef"
          v-model="text"
          class="source"
          :placeholder="t('pages.wiki.editor.contentPlaceholder')"
          spellcheck="false"
          @input="onTextareaInput"
          @scroll="syncScroll"
        ></textarea>
      </div>

      <div
        class="splitter"
        role="separator"
        aria-orientation="vertical"
        :aria-label="t('pages.wiki.editor.resize')"
        :title="t('pages.wiki.editor.resize')"
        @pointerdown="onDividerPointerDown"
      >
        <GripVertical :size="14" />
      </div>

      <div class="pane preview-pane">
        <div ref="previewRef" class="preview-scroll">
          <WikiMarkdown :content="previewText" />
        </div>
      </div>
    </div>

    <!-- 底部拖拽条：拉长/缩短双栏高度（最短为默认高度） -->
    <div
      class="height-splitter"
      :class="{ active: draggingH }"
      role="separator"
      aria-orientation="horizontal"
      :aria-label="t('pages.wiki.editor.resizeH')"
      :title="t('pages.wiki.editor.resizeH')"
      @pointerdown="onHeightPointerDown"
    >
      <GripHorizontal :size="16" />
    </div>

    <!-- 冲突弹窗 -->
    <div v-if="conflict" class="conflict-mask">
      <div class="conflict-box">
        <AlertTriangle :size="26" class="conflict-icon" />
        <h3 class="conflict-title">{{ t('pages.wiki.editor.conflict') }}</h3>
        <p class="conflict-desc">{{ t('pages.wiki.editor.conflictDesc') }}</p>
        <div class="conflict-actions">
          <button type="button" class="conflict-btn" @click="loadLatest">
            {{ t('pages.wiki.editor.loadLatest') }}
          </button>
          <button type="button" class="conflict-btn primary" @click="forceSave">
            {{ t('pages.wiki.editor.forceSave') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-perm {
  min-height: 50vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--links-color);
}

.editor {
  min-width: 0;
  /* 全宽内容区中水平居中（双栏编辑） */
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}

/* 顶部 */
.editor-top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.top-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--float-bg);
  border-radius: 9px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.top-btn:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.slug-input {
  flex: 1;
  min-width: 180px;
  max-width: 340px;
  padding: 8px 12px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: var(--card-color);
  color: var(--text-color);
  font-size: 14px;
  font-family: Consolas, 'Courier New', monospace;
  outline: none;
}

.slug-input:focus {
  border-color: var(--notice-color);
}

.slug-input.error {
  border-color: #e5484d;
}

.slug-error {
  font-size: 12px;
  color: #e5484d;
}

.slug-warn {
  font-size: 12px;
  color: var(--notice-color);
}

.saved-tag,
.dirty-tag {
  font-size: 12px;
  color: var(--links-color);
}

.dirty-tag::before {
  content: '•';
  color: var(--notice-color);
  margin-right: 4px;
}

/* 顶部右侧操作组：撤销 + 保存 */
.top-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.undo-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--links-color);
  font-size: 13.5px;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.undo-btn:hover:not(:disabled) {
  background: var(--float-bg);
  color: var(--text-color);
}

.undo-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.save-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: none;
  border-radius: 10px;
  background: var(--notice-color);
  color: var(--text-color);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s ease, opacity 0.15s ease;
}

.save-btn:hover {
  filter: brightness(1.06);
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

/* 编辑摘要行（顶部栏之下、工具条之上） */
.summary-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}

.summary-input {
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
  padding: 9px 14px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: var(--card-color);
  color: var(--text-color);
  font-size: 13.5px;
  outline: none;
}

.summary-input:focus {
  border-color: var(--notice-color);
}

/* 消歧义页勾选 */
.disambig-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--links-color);
  cursor: pointer;
  user-select: none;
}

.disambig-check input {
  accent-color: var(--notice-color);
  cursor: pointer;
}

/* 工具条 */
.toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 14px;
  padding: 6px 8px;
  border: 1px solid var(--float-bg);
  border-radius: 12px;
  background: var(--card-color);
  flex-wrap: wrap;
}

.tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.tool-btn:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.tool-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* 隐藏的文件选择框（由上传按钮触发） */
.file-input {
  display: none;
}

.tool-italic {
  font-family: Georgia, serif;
  font-style: italic;
  font-weight: 700;
}

.tool-h {
  font-size: 13px;
  font-weight: 700;
}

/* H1-H6 下拉 */
.tool-dd {
  position: relative;
  display: flex;
}

.dd-trigger {
  gap: 1px;
}

.dd-trigger.active {
  background: var(--float-bg);
  color: var(--text-color);
}

.dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 30;
  min-width: 148px;
  padding: 5px;
  border: 1px solid var(--float-bg);
  border-radius: 12px;
  background: var(--card-color);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.14);
  display: flex;
  flex-direction: column;
}

.dd-item {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 5px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.dd-item:hover {
  background: var(--float-bg);
}

.dd-h {
  font-weight: 700;
  line-height: 1.3;
}

.dd-h.is-h1 { font-size: 19px; }
.dd-h.is-h2 { font-size: 17px; }
.dd-h.is-h3 { font-size: 15.5px; }
.dd-h.is-h4 { font-size: 14px; }
.dd-h.is-h5 { font-size: 13px; }
.dd-h.is-h6 { font-size: 12px; }

.dd-enter-active,
.dd-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dd-enter-from,
.dd-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.tool-sep {
  width: 1px;
  height: 18px;
  margin: 0 4px;
  background: var(--float-bg);
}

.tool-spacer {
  flex: 1;
}

.char-count {
  font-size: 12px;
  color: var(--links-color);
  padding: 0 8px;
  white-space: nowrap;
}

/* 双栏：源码 | 可拖拽分隔条 | 预览 */
.panes {
  display: flex;
  align-items: stretch;
  margin-top: 14px;
}

.panes.dragging {
  user-select: none;
  cursor: col-resize;
}

.pane {
  min-width: 0;
  /* 默认高度 = 视口高度 - 320px；--extra-h 为底部拖拽的增量（≥0，最小即默认高度） */
  height: calc(100vh - 320px + var(--extra-h, 0px));
  min-height: 320px;
  border: 1px solid var(--float-bg);
  border-radius: 14px;
  background: var(--card-color);
  overflow: hidden;
}

/* 源码栏宽度由 --source-w（拖拽比例）控制 */
.pane-source {
  flex: 0 0 auto;
  width: var(--source-w, 50%);
}

.preview-pane {
  flex: 1;
}

/* 拖拽分隔条 */
.splitter {
  flex-shrink: 0;
  width: 16px;
  margin: 0 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: col-resize;
  color: var(--links-color);
  opacity: 0.55;
  border-radius: 8px;
  touch-action: none;
  user-select: none;
  transition: background-color 0.15s ease, opacity 0.15s ease, color 0.15s ease;
}

.splitter:hover,
.panes.dragging .splitter {
  opacity: 1;
  background: var(--float-bg);
  color: var(--text-color);
}

/* 底部拖拽条：调整双栏整体高度（横贯全宽） */
.height-splitter {
  height: 16px;
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: row-resize;
  color: var(--links-color);
  opacity: 0.55;
  border-radius: 8px;
  touch-action: none;
  user-select: none;
  transition: background-color 0.15s ease, opacity 0.15s ease, color 0.15s ease;
}

.height-splitter:hover,
.height-splitter.active {
  opacity: 1;
  background: var(--float-bg);
  color: var(--text-color);
}

.source {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding: 16px;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--text-color);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 13.5px;
  line-height: 1.7;
}

.preview-pane {
  background: transparent;
}

.preview-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 16px 18px;
  box-sizing: border-box;
}

/* 冲突弹窗 */
.conflict-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.conflict-box {
  width: min(420px, 90vw);
  padding: 28px 26px;
  border-radius: 16px;
  background: var(--card-color);
  text-align: center;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.2);
}

.conflict-icon {
  color: var(--notice-color);
  margin-bottom: 10px;
}

.conflict-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.conflict-desc {
  margin: 0 0 20px;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--links-color);
}

.conflict-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.conflict-btn {
  padding: 9px 18px;
  border: 1px solid var(--float-bg);
  border-radius: 10px;
  background: transparent;
  color: var(--text-color);
  font-size: 13.5px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.conflict-btn:hover {
  background: var(--float-bg);
}

.conflict-btn.primary {
  background: var(--notice-color);
  border-color: transparent;
  font-weight: 600;
}

@media (max-width: 1023px) {
  .editor {
    padding: 0 16px;
  }
}

@media (max-width: 860px) {
  /* 窄屏：双栏上下堆叠，隐藏拖拽分隔条与高度拖拽条 */
  .panes {
    flex-direction: column;
  }

  .pane-source {
    width: 100%;
  }

  .splitter,
  .height-splitter {
    display: none;
  }

  .pane {
    height: 42vh;
  }
}
</style>

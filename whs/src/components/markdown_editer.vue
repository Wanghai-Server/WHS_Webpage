<script setup>
/**
 * 全站通用 Markdown 编辑器（可复用组件）。
 *
 * - GitHub 风格：Write / Preview 切换，语法提示工具条（仿 Wiki 编辑器）；
 * - 支持上传图片 / 视频 / 音频（类型与大小同 Wiki），可点击上传、粘贴文件、拖拽到组件内上传；
 * - 上传文件保存到独立目录（/api/markdown/upload）；
 * - multilingual=true 时提供编辑语言切换：v-model 为 { zh, en } 对象，
 *   编辑与编辑预览使用当前选择语言；站点展示时始终跟随网站语言；
 * - 可用 lang 受控指定编辑语言，并用 showLangSwitch=false 隐藏组件内置切换，
 *   由父组件统一控制标题 / 正文的语言（如系统消息发布框）；
 * - 预览使用全站统一 Markdown 渲染管线（colorCodes / LaTeX / mermaid / 代码高亮）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Bold,
  Code,
  Image,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  ListTodo,
  Minus,
  Palette,
  Paperclip,
  Quote,
  SquareCode,
  Strikethrough,
  Table,
  Upload,
  ChevronDown,
} from 'lucide-vue-next'
import MarkdownView from './markdown_view.vue'
import Tabs from './tabs.vue'
import { MC_COLORS } from '../composables/markdown/colorCodes'
import { useMarkdownInsert, buildMediaMarkdown } from '../composables/markdown/insert'
import {
  MARKDOWN_UPLOAD_ACCEPT,
  MARKDOWN_UPLOAD_LIMITS,
  mediaKindOf,
  uploadMarkdownFile,
} from '../composables/markdown/upload'
import { useTips } from '../composables/useTips'

const props = defineProps({
  modelValue: { type: [String, Object], default: '' },
  // true：内容为 { zh, en } 多语言对象，并提供编辑语言切换
  multilingual: { type: Boolean, default: false },
  // 受控编辑语言（'zh' / 'en'）；为空时使用组件内部状态（默认跟随站点语言）
  lang: { type: String, default: '' },
  // false：隐藏组件内置的“中文 / English”切换，由父组件统一控制
  showLangSwitch: { type: Boolean, default: true },
  placeholder: { type: String, default: '' },
  minHeight: { type: Number, default: 220 },
  disabled: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'update:lang'])

const { t, locale } = useI18n()
const { showTip } = useTips()

const LANGS = ['zh', 'en']
const LANG_LABELS = { zh: '中文', en: 'English' }

const mode = ref('write') // 'write' | 'preview'
const innerLang = ref(locale.value === 'en' ? 'en' : 'zh')
const editLang = computed(() =>
  props.lang === 'zh' || props.lang === 'en' ? props.lang : innerLang.value
)

function selectLang(lang) {
  innerLang.value = lang
  emit('update:lang', lang)
}
const drafts = ref({ zh: '', en: '' })
const taRef = ref(null)
const fileInputRef = ref(null)
const uploading = ref(false)
const dragOver = ref(false)
let dragDepth = 0

// 多语言：同步外部对象；外部若误传字符串，则视为当前编辑语言的内容
function normalizeDraft(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return { zh: String(value.zh || ''), en: String(value.en || '') }
  }
  const next = { zh: '', en: '' }
  next[editLang.value] = typeof value === 'string' ? value : ''
  return next
}

function syncDraft(value) {
  const next = normalizeDraft(value)
  if (next.zh === drafts.value.zh && next.en === drafts.value.en) return
  drafts.value = next
}

syncDraft(props.modelValue)

// 父组件异步回填（编辑已有内容）时同步多语言草稿
const stopWatch = watch(
  () => props.modelValue,
  (value) => {
    if (props.multilingual) syncDraft(value)
  },
  { deep: true }
)

const localText = computed({
  get() {
    if (props.multilingual) return drafts.value[editLang.value] || ''
    return typeof props.modelValue === 'string' ? props.modelValue : ''
  },
  set(value) {
    if (props.multilingual) {
      drafts.value = { ...drafts.value, [editLang.value]: value }
      emit('update:modelValue', { zh: drafts.value.zh, en: drafts.value.en })
    } else {
      emit('update:modelValue', value)
    }
  },
})

const charCount = computed(() => localText.value.replace(/\s/g, '').length)

// 编辑 / 预览：复用站内 Tabs 导航组件（下划线式标签栏）
const modeTabs = computed(() => [
  { key: 'write', label: t('markdown.write') },
  { key: 'preview', label: t('markdown.preview') },
])

// ---------------- 语法提示工具条 ----------------

const { wrapSelection, insertLine, insertBlock, insertHeading, insertTable, insertLink, insertImage, insertColorCode } = useMarkdownInsert(localText, taRef)

const headingsOpen = ref(false)
const colorsOpen = ref(false)
const mcColors = MC_COLORS

function toggleHeadings() {
  colorsOpen.value = false
  headingsOpen.value = !headingsOpen.value
}

function toggleColors() {
  headingsOpen.value = false
  colorsOpen.value = !colorsOpen.value
}

function pickHeading(n) {
  headingsOpen.value = false
  insertHeading(n)
}

function pickColor(code) {
  colorsOpen.value = false
  insertColorCode(code)
}

function onDocClick(e) {
  if (!(e.target.closest && e.target.closest('.md-dd'))) {
    headingsOpen.value = false
    colorsOpen.value = false
  }
}

// ---------------- 上传（点击 / 粘贴 / 拖拽） ----------------

function pickFile() {
  if (props.disabled || uploading.value) return
  fileInputRef.value?.click()
}

function onFileChange(e) {
  const files = e.target.files ? Array.from(e.target.files) : []
  e.target.value = ''
  handleFiles(files)
}

async function handleFiles(files) {
  if (props.disabled || uploading.value) return
  const list = Array.from(files || [])
  if (!list.length) return
  if (mode.value !== 'write') mode.value = 'write'
  await nextTick()
  for (const file of list) {
    const kind = mediaKindOf(file)
    if (!kind) {
      showTip('error', t('markdown.unsupportedFile'))
      continue
    }
    if (file.size > MARKDOWN_UPLOAD_LIMITS[kind]) {
      showTip('error', t('markdown.fileTooLarge'))
      continue
    }
    uploading.value = true
    try {
      const data = await uploadMarkdownFile(file)
      insertBlock(buildMediaMarkdown(data.url, data.type))
    } catch (err) {
      showTip('error', (err && err.message) || t('markdown.uploadFailed'))
    } finally {
      uploading.value = false
    }
  }
}

function hasFiles(e) {
  const types = e.dataTransfer && e.dataTransfer.types
  return !!types && Array.from(types).includes('Files')
}

function onDragEnter(e) {
  if (!hasFiles(e)) return
  e.preventDefault()
  dragDepth += 1
  dragOver.value = true
}

function onDragOver(e) {
  if (!hasFiles(e)) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
}

function onDragLeave(e) {
  if (!hasFiles(e)) return
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragOver.value = false
}

function onDrop(e) {
  if (!hasFiles(e)) return
  e.preventDefault()
  dragDepth = 0
  dragOver.value = false
  handleFiles(e.dataTransfer && e.dataTransfer.files)
}

function onPaste(e) {
  const files = e.clipboardData && e.clipboardData.files
  if (files && files.length) {
    e.preventDefault()
    handleFiles(files)
  }
}

// 供父组件聚焦（如个人资料编辑弹窗）
function focus() {
  mode.value = 'write'
  nextTick(() => taRef.value?.focus())
}

// 组件外（如对话框其他区域）拖入文件时阻止浏览器默认打开文件；
// 上传范围仍限定在本组件内（见根节点上的 drag/drop 处理）
function onDocDragOver(e) {
  if (hasFiles(e)) e.preventDefault()
}

function onDocDrop(e) {
  if (hasFiles(e)) e.preventDefault()
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('dragover', onDocDragOver)
  document.addEventListener('drop', onDocDrop)
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('dragover', onDocDragOver)
  document.removeEventListener('drop', onDocDrop)
  stopWatch && stopWatch()
})

defineExpose({ focus })
</script>

<template>
  <div
    class="md-editor"
    :class="{ 'is-dragover': dragOver, 'is-disabled': disabled }"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="md-editor-head">
      <div class="md-tabs">
        <Tabs v-model="mode" :items="modeTabs" />
      </div>

      <!-- 多语言：编辑语言切换（只影响编辑与编辑预览） -->
      <div
        v-if="multilingual && showLangSwitch"
        class="md-langs"
        role="group"
        :aria-label="t('markdown.language')"
      >
        <span class="md-langs-label">{{ t('markdown.language') }}</span>
        <button
          v-for="l in LANGS"
          :key="l"
          type="button"
          class="md-lang"
          :class="{ active: editLang === l }"
          @click="selectLang(l)"
        >{{ LANG_LABELS[l] }}</button>
      </div>

      <div v-if="mode === 'write'" class="md-tools">
        <!-- H1-H6 -->
        <div class="md-dd">
          <button type="button" class="md-tool dd-trigger" :class="{ active: headingsOpen }" title="H" @click="toggleHeadings">
            <span class="md-h">H</span>
            <ChevronDown :size="11" />
          </button>
          <Transition name="md-dd">
            <div v-if="headingsOpen" class="md-menu md-menu-headings">
              <button v-for="n in 6" :key="n" type="button" class="md-menu-item" @click="pickHeading(n)">
                <span class="md-h" :class="`is-h${n}`">H{{ n }}</span>
              </button>
            </div>
          </Transition>
        </div>

        <span class="md-sep"></span>

        <button type="button" class="md-tool" title="**" @click="wrapSelection('**', '**', '加粗')">
          <Bold :size="15" />
        </button>
        <button type="button" class="md-tool" title="*" @click="wrapSelection('*', '*', '斜体')">
          <Italic :size="15" />
        </button>
        <button type="button" class="md-tool" title="~~" @click="wrapSelection('~~', '~~', '删除线')">
          <Strikethrough :size="15" />
        </button>
        <button type="button" class="md-tool" title="`" @click="wrapSelection('`', '`', 'code')">
          <Code :size="15" />
        </button>
        <button type="button" class="md-tool" title="```" @click="wrapSelection('```\n', '\n```', '代码')">
          <SquareCode :size="15" />
        </button>

        <!-- § 颜色 / 格式代码 -->
        <div class="md-dd">
          <button type="button" class="md-tool dd-trigger" :class="{ active: colorsOpen }" :title="t('pages.wiki.editor.color')" @click="toggleColors">
            <Palette :size="15" />
            <ChevronDown :size="11" />
          </button>
          <Transition name="md-dd">
            <div v-if="colorsOpen" class="md-menu md-menu-colors">
              <button
                v-for="c in mcColors"
                :key="c.code"
                type="button"
                class="md-color-swatch"
                :style="{ backgroundColor: c.hex }"
                :title="`§${c.code} ${t('pages.wiki.editor.colors.' + c.name)}`"
                :aria-label="`§${c.code} ${t('pages.wiki.editor.colors.' + c.name)}`"
                @click="pickColor(c.code)"
              ></button>
              <button type="button" class="md-color-reset" @click="pickColor('r')">
                §r {{ t('pages.wiki.editor.colorReset') }}
              </button>
            </div>
          </Transition>
        </div>

        <span class="md-sep"></span>

        <button type="button" class="md-tool" title="link" @click="insertLink">
          <LinkIcon :size="15" />
        </button>
        <button type="button" class="md-tool" title="image" @click="insertImage">
          <Image :size="15" />
        </button>
        <button type="button" class="md-tool" title="quote" @click="insertLine('> ')">
          <Quote :size="15" />
        </button>
        <button type="button" class="md-tool" title="list" @click="insertLine('- ')">
          <List :size="15" />
        </button>
        <button type="button" class="md-tool" title="1." @click="insertLine('1. ')">
          <ListOrdered :size="15" />
        </button>
        <button type="button" class="md-tool" title="- [ ]" @click="insertLine('- [ ] ')">
          <ListTodo :size="15" />
        </button>
        <button type="button" class="md-tool" title="table" @click="insertTable">
          <Table :size="15" />
        </button>
        <button type="button" class="md-tool" title="---" @click="insertLine('---', false)">
          <Minus :size="15" />
        </button>
      </div>
    </div>

    <div class="md-editor-body">
      <textarea
        v-if="mode === 'write'"
        ref="taRef"
        v-model="localText"
        class="md-textarea"
        :style="{ minHeight: `${minHeight}px` }"
        :placeholder="placeholder || t('markdown.placeholder')"
        :disabled="disabled"
        :aria-label="ariaLabel || t('markdown.editorAria')"
        spellcheck="false"
        @paste="onPaste"
      ></textarea>
      <div v-else class="md-preview">
        <MarkdownView :content="localText" />
      </div>
    </div>

    <div v-if="mode === 'write'" class="md-editor-foot">
      <button
        type="button"
        class="md-upload-hint"
        :disabled="disabled || uploading"
        @click="pickFile"
      >
        <Paperclip :size="14" />
        <span>{{ uploading ? t('markdown.uploading') : t('markdown.uploadHint') }}</span>
      </button>
      <span class="md-count">{{ charCount }} {{ t('markdown.charCountUnit') }}</span>
    </div>

    <input
      ref="fileInputRef"
      type="file"
      class="md-file-input"
      multiple
      hidden
      :accept="MARKDOWN_UPLOAD_ACCEPT"
      @change="onFileChange"
    />

    <div v-if="dragOver" class="md-drop-mask" aria-hidden="true">
      <Upload :size="26" />
      <span>{{ t('markdown.dropHint') }}</span>
    </div>
  </div>
</template>

<style scoped>
.md-editor {
  position: relative;
  border: 1px solid var(--float-bg);
  border-radius: 12px;
  background: var(--card-color);
  overflow: hidden;
  transition: border-color 0.15s ease;
}

.md-editor:focus-within {
  border-color: rgba(148, 163, 184, 0.45);
}

.md-editor.is-disabled {
  opacity: 0.6;
  pointer-events: none;
}

/* 头部：Write / Preview 标签 + 工具条 */
.md-editor-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--float-bg);
  background: var(--float-bg);
}

.md-tabs {
  flex-shrink: 0;
}

/* Tabs 复用站内下划线式导航，仅调整字号 / 内边距 / 底边以适配编辑器头部 */
.md-tabs :deep(.tabs) {
  border-bottom: none;
  gap: 2px;
}

.md-tabs :deep(.tabs-item) {
  /* 固定高度：中英文行高不同，避免编辑/预览切换时头部高度变化 */
  height: 30px;
  padding: 0 12px;
  font-size: 13.5px;
  font-weight: 600;
}

.md-tabs :deep(.tabs-indicator) {
  bottom: 0;
  height: 2px;
}
/* 多语言切换 */
.md-langs {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 4px;
}

.md-langs-label {
  font-size: 12px;
  color: var(--links-color);
}

.md-lang {
  padding: 4px 10px;
  border: 1px solid var(--float-bg);
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.md-lang:hover {
  color: var(--text-color);
}

.md-lang.active {
  color: var(--text-color);
  border-color: var(--notice-color);
}

/* 工具条 */
.md-tools {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  flex-wrap: wrap;
}

.md-tool {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 30px;
  height: 30px;
  padding: 0 4px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.md-tool:hover:not(:disabled) {
  background: var(--card-color);
  color: var(--text-color);
}

.md-tool:disabled {
  opacity: 0.5;
  cursor: default;
}

.md-tool.active {
  background: var(--card-color);
  color: var(--text-color);
}

.md-sep {
  width: 1px;
  height: 18px;
  margin: 0 3px;
  background: var(--float-bg);
}

.md-h {
  font-size: 13px;
  font-weight: 700;
}

.md-h.is-h1 { font-size: 19px; }
.md-h.is-h2 { font-size: 17px; }
.md-h.is-h3 { font-size: 15.5px; }
.md-h.is-h4 { font-size: 14px; }
.md-h.is-h5 { font-size: 13px; }
.md-h.is-h6 { font-size: 12px; }

/* 下拉菜单 */
.md-dd {
  position: relative;
  display: flex;
}

.md-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 30;
  padding: 5px;
  border: 1px solid var(--float-bg);
  border-radius: 12px;
  background: var(--card-color);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.14);
}

.md-menu-headings {
  min-width: 84px;
  display: flex;
  flex-direction: column;
}

.md-menu-item {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 5px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
}

.md-menu-item:hover {
  background: var(--float-bg);
}

.md-menu-colors {
  display: grid;
  grid-template-columns: repeat(4, 22px);
  gap: 6px;
  min-width: 0;
}

.md-color-swatch {
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid rgba(148, 163, 184, 0.4);
  border-radius: 6px;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.md-color-swatch:hover {
  transform: scale(1.12);
  box-shadow: 0 0 0 2px var(--notice-color);
}

.md-color-reset {
  grid-column: 1 / -1;
  margin-top: 2px;
  padding: 4px 8px;
  border: none;
  border-radius: 8px;
  background: var(--float-bg);
  color: var(--text-color);
  font: inherit;
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.md-color-reset:hover {
  background: var(--notice-color);
}

.md-dd-enter-active,
.md-dd-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.md-dd-enter-from,
.md-dd-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* 正文：编辑 + 预览 */
.md-editor-body {
  min-width: 0;
}

.md-textarea {
  display: block;
  width: 100%;
  box-sizing: border-box;
  padding: 14px 16px;
  border: none;
  outline: none;
  resize: vertical;
  background: transparent;
  color: var(--text-color);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 13.5px;
  line-height: 1.7;
}

.md-textarea::placeholder {
  color: var(--links-color);
}

.md-preview {
  max-height: 60vh;
  overflow-y: auto;
  padding: 14px 16px;
}

/* 底部：上传提示 + 字数 */
.md-editor-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-top: 1px solid var(--float-bg);
  background: var(--float-bg);
}

.md-upload-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  transition: color 0.15s ease;
}

.md-upload-hint:hover:not(:disabled) {
  color: var(--text-color);
}

.md-upload-hint:disabled {
  opacity: 0.6;
  cursor: default;
}

.md-count {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--links-color);
  white-space: nowrap;
}

/* 拖拽上传蒙层（范围为本组件区域） */
.md-drop-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 2px dashed var(--notice-color);
  border-radius: 12px;
  background: rgba(11, 29, 58, 0.72);
  color: #f5f5f5;
  font-size: 14px;
  pointer-events: none;
}

.md-file-input {
  display: none;
}
</style>

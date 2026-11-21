/**
 * Markdown 编辑器共享插入工具。
 *
 * 封装"在光标处插入 / 包裹选区 / 插入行 / 插入链接图片 / 插入表格 /
 * 插入 § 颜色代码"等语法提示操作，供 Markdown 编辑器与 Wiki 编辑器复用，
 * 保证光标位置、滚动位置与撤销行为一致。
 *
 * 用法：
 *   const { wrapSelection, insertLine, ... } = useMarkdownInsert(textRef, textareaRef, {
 *     beforeChange: pushUndo,     // 可选：变更前记录撤销快照
 *     afterChange: markStable,    // 可选：变更后清理键入跟踪
 *   })
 */
import { nextTick } from 'vue'
import i18n from '../../i18n'

/** 生成媒体 Markdown 片段（图片/视频/音频统一使用图片语法，由渲染管线按扩展名区分）。 */
export function buildMediaMarkdown(url, type) {
  const key =
    type === 'video'
      ? 'markdown.mediaVideo'
      : type === 'audio'
        ? 'markdown.mediaAudio'
        : 'markdown.mediaImage'
  const alt = i18n.global.t(key)
  return `![${alt}](${url})`
}

export function useMarkdownInsert(textRef, taRef, hooks = {}) {
  const beforeChange = () => hooks.beforeChange && hooks.beforeChange()
  const afterChange = () => hooks.afterChange && hooks.afterChange()

  // 变更后恢复焦点 / 选区 / 滚动位置
  function restore(selectionStart, selectionEnd, scrollTop) {
    nextTick(() => {
      const el = taRef.value
      if (!el) return
      el.focus()
      el.setSelectionRange(selectionStart, selectionEnd)
      el.scrollTop = scrollTop
    })
  }

  // 包裹选区（无选中时插入占位文字并选中）
  function wrapSelection(before, after, placeholder) {
    const ta = taRef.value
    if (!ta) return
    beforeChange()
    const scrollTop = ta.scrollTop
    const { selectionStart: s, selectionEnd: e } = ta
    const selected = textRef.value.slice(s, e) || placeholder || ''
    textRef.value = textRef.value.slice(0, s) + before + selected + after + textRef.value.slice(e)
    afterChange()
    restore(s + before.length, s + before.length + selected.length, scrollTop)
  }

  // 新起一行插入内容（默认结尾追加换行）
  function insertLine(line, extraNewline = true) {
    const ta = taRef.value
    if (!ta) return
    beforeChange()
    const scrollTop = ta.scrollTop
    const s = ta.selectionStart
    const before = textRef.value.slice(0, s)
    const nl = before.length && !before.endsWith('\n') ? '\n' : ''
    const suffix = extraNewline ? '\n' : ''
    textRef.value = before + nl + line + suffix + textRef.value.slice(s)
    afterChange()
    restore(s + nl.length + line.length, s + nl.length + line.length, scrollTop)
  }

  // 在光标处插入一段 Markdown（不带额外换行）
  function insertAtCursor(markdown) {
    const ta = taRef.value
    if (!ta) return
    beforeChange()
    const scrollTop = ta.scrollTop
    const s = ta.selectionStart
    const e = ta.selectionEnd
    textRef.value = textRef.value.slice(0, s) + markdown + textRef.value.slice(e)
    afterChange()
    restore(s + markdown.length, s + markdown.length, scrollTop)
  }

  // 在光标处插入独立块（前后自动补换行，避免图片/媒体语法粘在代码块等结构上）
  function insertBlock(markdown) {
    const ta = taRef.value
    if (!ta) return
    const before = textRef.value.slice(0, ta.selectionStart)
    const prefix = before.length && !before.endsWith('\n') ? '\n' : ''
    insertAtCursor(`${prefix}${markdown}\n`)
  }

  function insertHeading(n) {
    insertLine('#'.repeat(n) + ' ')
  }

  function insertTable() {
    insertLine('| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n|  |  |  |', false)
  }

  function insertLink() {
    const ta = taRef.value
    if (!ta) return
    beforeChange()
    const scrollTop = ta.scrollTop
    const s = ta.selectionStart
    const e = ta.selectionEnd
    const selected = textRef.value.slice(s, e)
    const markdown = selected ? `[${selected}](https://)` : '[链接](https://)'
    textRef.value = textRef.value.slice(0, s) + markdown + textRef.value.slice(e)
    afterChange()
    restore(s, s + markdown.length, scrollTop)
  }

  function insertImage() {
    const ta = taRef.value
    if (!ta) return
    beforeChange()
    const scrollTop = ta.scrollTop
    const s = ta.selectionStart
    const e = ta.selectionEnd
    const selected = textRef.value.slice(s, e)
    const markdown = selected ? `![${selected}](https://)` : '![图片描述](https://)'
    textRef.value = textRef.value.slice(0, s) + markdown + textRef.value.slice(e)
    afterChange()
    restore(s, s + markdown.length, scrollTop)
  }

  // § 颜色 / 格式代码：有选中时只作用于选中部分
  function insertColorCode(code) {
    const ta = taRef.value
    if (!ta) return
    beforeChange()
    const scrollTop = ta.scrollTop
    const s = ta.selectionStart
    const e = ta.selectionEnd
    const selected = textRef.value.slice(s, e)
    const prefix = `§${code}`
    const insert = selected ? `${prefix}${selected}§r` : prefix
    textRef.value = textRef.value.slice(0, s) + insert + textRef.value.slice(e)
    afterChange()
    restore(s + prefix.length, s + prefix.length + selected.length, scrollTop)
  }

  return {
    wrapSelection,
    insertLine,
    insertAtCursor,
    insertBlock,
    insertHeading,
    insertTable,
    insertLink,
    insertImage,
    insertColorCode,
  }
}

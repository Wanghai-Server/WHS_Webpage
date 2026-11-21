/**
 * Markdown 编辑器上传工具。
 *
 * - 允许类型 / 大小限制与 Wiki 媒体上传一致（后端共用 api/media_upload.py）；
 * - 上传到独立目录 data/markdown_upload/（接口 /api/markdown/upload）；
 * - 登录用户即可上传（与 Wiki 上传要求的权限不同）。
 */
import i18n from '../../i18n'

export const MARKDOWN_IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'webp', 'gif']
export const MARKDOWN_VIDEO_EXTS = ['mp4', 'webm', 'mov']
export const MARKDOWN_AUDIO_EXTS = ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac']
export const MARKDOWN_UPLOAD_EXTS = [
  ...MARKDOWN_IMAGE_EXTS,
  ...MARKDOWN_VIDEO_EXTS,
  ...MARKDOWN_AUDIO_EXTS,
]

// file input 的 accept：与 Wiki 上传按钮一致
export const MARKDOWN_UPLOAD_ACCEPT = MARKDOWN_UPLOAD_EXTS.map((ext) => `.${ext}`).join(',')

// 与后端 / Wiki 一致的类型大小上限（字节），用于上传前快速提示
export const MARKDOWN_UPLOAD_LIMITS = {
  image: 5 * 1024 * 1024,
  video: 50 * 1024 * 1024,
  audio: 20 * 1024 * 1024,
}

function fileExt(name) {
  const base = String(name || '').split('/').pop().split('\\').pop()
  return (base.includes('.') ? base.split('.').pop() : '').toLowerCase()
}

/** 文件对应的媒体类型（image / video / audio）；不支持时返回 ''。 */
export function mediaKindOf(file) {
  const ext = fileExt(file && file.name)
  if (MARKDOWN_IMAGE_EXTS.includes(ext)) return 'image'
  if (MARKDOWN_VIDEO_EXTS.includes(ext)) return 'video'
  if (MARKDOWN_AUDIO_EXTS.includes(ext)) return 'audio'
  return ''
}

export function isSupportedMediaFile(file) {
  return !!mediaKindOf(file)
}

function localMessage(data) {
  const message = data && data.message
  if (!message) return ''
  const locale = i18n.global.locale.value
  return message[locale] || message.zh || message.en || ''
}

/**
 * 上传媒体文件到 /api/markdown/upload。
 * @returns {Promise<{url: string, type: 'image'|'video'|'audio', original: string}>}
 */
export async function uploadMarkdownFile(file) {
  const token = localStorage.getItem('token')
  const form = new FormData()
  form.append('file', file)
  let res
  try {
    res = await fetch('/api/markdown/upload', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    })
  } catch {
    throw new Error(i18n.global.t('markdown.uploadFailed'))
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok || !data || !data.url) {
    throw new Error(localMessage(data) || i18n.global.t('markdown.uploadFailed'))
  }
  return data
}

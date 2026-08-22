/**
 * 维基 API 封装：/api/wiki/* 的 fetch 客户端。
 *
 * - 自动附带 Authorization: Bearer <token>（未登录则不带）；
 * - 语言切换实时生效：内容类接口携带 lang 参数（zh/en），切换语言时
 *   重新向后端请求对应语言的数据（界面文案由 vue-i18n 提供，不走这里）；
 * - 错误统一抛 WikiApiError（含后端稳定错误码 code 与当前语言消息），
 *   供页面按 code 做分支处理（如 wiki_revision_conflict）。
 */
import i18n from '../../i18n'

const BASE = '/api/wiki'

export class WikiApiError extends Error {
  constructor(code, status, message) {
    super(message || `HTTP ${status}`)
    this.name = 'WikiApiError'
    this.code = code
    this.status = status
  }
}

// slug 含 '/' 层级，逐段编码避免特殊字符问题
function encodePath(slug) {
  return String(slug || '')
    .split('/')
    .map((seg) => encodeURIComponent(seg))
    .join('/')
}

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function localMessage(data) {
  const m = data && data.message
  if (!m) return ''
  const loc = i18n.global.locale.value
  return m[loc] || m.zh || m.en || ''
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...authHeaders(),
      },
    })
  } catch (err) {
    throw new WikiApiError('network_error', 0, err instanceof Error ? err.message : 'Network error')
  }
  let data = null
  try {
    data = await res.json()
  } catch {
    /* 非 JSON 响应 */
  }
  if (!res.ok) {
    throw new WikiApiError(
      (data && data.code) || 'unknown',
      res.status,
      localMessage(data) || `HTTP ${res.status}`
    )
  }
  return data
}

const jsonOptions = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const wikiApi = {
  listPages: () => request('/pages'),

  getPage: (slug, lang) => request(`/page/${encodePath(slug)}?lang=${lang || 'zh'}`),

  getHistory: (slug, lang) => request(`/page/${encodePath(slug)}/history?lang=${lang || 'zh'}`),

  getRevision: (revId) => request(`/revision/${revId}`),

  search: (q, lang) => request(`/search?q=${encodeURIComponent(q || '')}&lang=${lang || 'zh'}`),

  createPage: (slug, content, lang, disambig = false) =>
    request('/page', jsonOptions('POST', { slug, content, lang: lang || 'zh', disambig })),

  updatePage: (slug, content, lang, baseRev, summary, disambig) =>
    request(`/page/${encodePath(slug)}`, jsonOptions('PUT', {
      content,
      lang: lang || 'zh',
      base_rev: baseRev,
      summary,
      disambig,
    })),

  // 重定向（管理接口；页面改名后旧路径自动跳转）
  createRedirect: (fromSlug, toSlug) =>
    request('/redirects', jsonOptions('POST', { from_slug: fromSlug, to_slug: toSlug })),
  deleteRedirect: (fromSlug) => request(`/redirects/${encodePath(fromSlug)}`, { method: 'DELETE' }),
  listRedirects: () => request('/redirects'),

  // 调整页面最小编辑权限（2/3/4；仅管理员）
  setPermission: (slug, value) =>
    request(`/page/${encodePath(slug)}/permission`, jsonOptions('PUT', { min_permission: value })),

  // 上传媒体文件（图片/视频/音频），返回 {url, type, original}
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/upload', { method: 'POST', body: form })
  },

  deletePage: (slug) => request(`/page/${encodePath(slug)}`, { method: 'DELETE' }),

  restoreRevision: (revId) => request(`/revision/${revId}/restore`, { method: 'POST' }),
}


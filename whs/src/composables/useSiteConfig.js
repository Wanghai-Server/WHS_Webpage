import { ref } from 'vue'

// 模块级单例：站点公开配置（/api/whs 返回的 title_suffix / hcaptcha_site_key / 301 等）。
// 路由守卫与 App.vue 共用同一份数据、同一时刻只发一个请求，
// 避免每个页面/组件各自请求 /api/whs。
const config = ref(null) // null = 尚未加载
let promise = null

async function load() {
  try {
    const res = await fetch('/api/whs')
    config.value = await res.json()
  } catch {
    console.error('Failed to load site config')
    config.value = {}
  }
}

// 尚未加载时触发一次加载，返回进行中的 promise（可为 null）
function ensureLoading() {
  if (config.value === null && !promise) {
    promise = load().finally(() => {
      promise = null
    })
  }
  return promise
}

// 组件中使用：返回响应式配置对象（读取时自动触发加载）
export function useSiteConfig() {
  ensureLoading()
  return config
}

// 路由守卫等非组件场景：等待配置就绪后返回配置值
export async function ensureSiteConfig() {
  const p = ensureLoading()
  if (p) await p
  return config.value || {}
}

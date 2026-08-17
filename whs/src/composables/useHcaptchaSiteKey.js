import { ref } from 'vue'

// 模块级单例：hCaptcha 公钥（site key），从后端 /api/whs 获取，避免前端硬编码
const siteKey = ref('')
let requested = false

export function useHcaptchaSiteKey() {
  if (!requested) {
    requested = true
    fetch('/api/whs')
      .then((res) => res.json())
      .then((data) => {
        siteKey.value = data.hcaptcha_site_key || ''
      })
      .catch((e) => {
        console.warn('Failed to load hCaptcha site key:', e)
      })
  }
  return siteKey
}

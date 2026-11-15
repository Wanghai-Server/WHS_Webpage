import { onUnmounted, ref } from 'vue'
import i18n from '../i18n'
import { useTips } from './useTips'

// 三段式邮箱：本地部分(字母/数字/_/./-)+ 单个@ + 域名(至少一个点)
export const EMAIL_RE = /^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/

const DEFAULT_COOLDOWN = 60

/**
 * 邮箱验证码发送的统一封装（注册 / 登录 / 找回密码 / 改密码 / 注销 / 改邮箱共用）。
 *
 * - 统一校验邮箱格式、是否已有人机验证 token、60 秒发送冷却与提示文案；
 * - 发送成功后调用传入的 resetCaptcha 重置人机验证控件（hCaptcha token 一次性）；
 * - 组件卸载时自动清理倒计时。
 *
 * @returns {{ sending: import('vue').Ref<boolean>, cooldown: import('vue').Ref<number>, send: Function, stopCooldown: Function }}
 */
export function useEmailCode() {
  const { showTip } = useTips()
  const sending = ref(false)
  const cooldown = ref(0)
  let timer = null

  function localMessage(data) {
    const m = data && data.message
    if (!m) return i18n.global.t('auth.request_failed')
    const loc = i18n.global.locale.value
    return m[loc] || m.zh || m.en || i18n.global.t('auth.request_failed')
  }

  function startCooldown(seconds = DEFAULT_COOLDOWN) {
    cooldown.value = seconds
    if (timer) clearInterval(timer)
    timer = setInterval(() => {
      cooldown.value -= 1
      if (cooldown.value <= 0) {
        clearInterval(timer)
        timer = null
      }
    }, 1000)
  }

  function stopCooldown() {
    if (timer) clearInterval(timer)
    timer = null
    cooldown.value = 0
  }

  /**
   * 发送邮箱验证码。
   *
   * @param {string} email 目标邮箱
   * @param {object} [options]
   * @param {string} [options.hcaptchaToken] 人机验证 token
   * @param {Function|null} [options.resetCaptcha] 发送成功后重置人机验证控件
   * @returns {Promise<{ ok: boolean, data?: object }>}
   */
  async function send(email, { hcaptchaToken = '', resetCaptcha = null } = {}) {
    const target = (email || '').trim()
    if (!EMAIL_RE.test(target)) {
      showTip('warning', i18n.global.t('auth.email_invalid'))
      return { ok: false }
    }
    // 必须先完成人机验证，才能获取验证码
    if (!hcaptchaToken) {
      showTip('warning', i18n.global.t('auth.captcha_required'))
      return { ok: false }
    }
    if (cooldown.value > 0 || sending.value) return { ok: false }
    sending.value = true
    let attempted = false
    try {
      attempted = true
      const res = await fetch('/api/user/send_code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: target,
          locale: i18n.global.locale.value,
          hcaptcha_response: hcaptchaToken,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.success) {
        showTip('info', i18n.global.t('auth.code_sent'))
        startCooldown()
        return { ok: true, data }
      }
      showTip('error', localMessage(data))
      return { ok: false, data }
    } catch (e) {
      showTip('error', i18n.global.t('auth.request_failed'))
      console.warn(e)
      return { ok: false }
    } finally {
      sending.value = false
      // hCaptcha token 一次性：无论成功失败，只要真的发起了请求就重置控件，
      // 避免下次发送复用已消费的 token（发送失败时后端已回滚冷却，可立即重试）。
      if (attempted && typeof resetCaptcha === 'function') resetCaptcha()
    }
  }

  onUnmounted(() => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  })

  return { sending, cooldown, send, stopCooldown }
}

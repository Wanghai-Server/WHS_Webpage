import { computed, ref } from 'vue'

const MIN_LENGTH = 8

// 密码允许的字符：ASCII（数字 / 字母 / 常见特殊字符均可；不含中文等非 ASCII）。
// 特殊字符不强制要求，但会参与下方强度等级（熵估算）的计算。
export const PASSWORD_ALLOWED_RE = /^[\x00-\x7F]+$/

// 硬性要求：至少 8 位、包含数字、同时包含大写和小写字母。
export function analyzePassword(password) {
  const value = password || ''
  return [
    { key: 'length', ok: value.length >= MIN_LENGTH },
    { key: 'digit', ok: /[0-9]/.test(value) },
    { key: 'case', ok: /[a-z]/.test(value) && /[A-Z]/.test(value) },
  ]
}

// 特殊字符（数字 / 字母以外的 ASCII 字符，如 !@#$%^&* 等）。
export function hasSpecialCharacter(password) {
  return /[^a-zA-Z0-9]/.test(password || '')
}

/**
 * 通用字符池熵估算：log2(字符池大小) × 长度。
 * 字符池按实际出现的字符类别累加（小写 26 / 大写 26 / 数字 10 / 其它特殊字符 33）。
 * 因此特殊字符虽然不强制，但会增大字符池、提高熵与强度等级。
 */
export function estimatePasswordEntropy(password) {
  const value = password || ''
  if (!value) return 0
  let pool = 0
  if (/[a-z]/.test(value)) pool += 26
  if (/[A-Z]/.test(value)) pool += 26
  if (/[0-9]/.test(value)) pool += 10
  if (hasSpecialCharacter(value)) pool += 33
  if (!pool) return 0
  return value.length * Math.log2(pool)
}

// 等级只在三条硬性要求全部满足后才存在；否则返回 null（不计算等级）。
export function getPasswordStrengthLevel(password, rules) {
  if (!rules.every((rule) => rule.ok)) return null
  const entropy = estimatePasswordEntropy(password)
  if (entropy >= 70) return 'high'
  if (entropy >= 50) return 'middle'
  return 'low'
}

// 进度条按三档取固定比例，较短的进度条即可区分低/中/高。
export const STRENGTH_PERCENT = { low: 33, middle: 66, high: 100 }

/**
 * 密码强度状态：
 * - rules：三条硬性要求 + 一条“特殊字符（可选）”检查项，供 UI 展示；
 *   未失焦前未满足项保持灰色，调用 touch() 后硬性要求未满足项标红，可选项永远不标红；
 * - hardRules：仅三条硬性要求，提交前用它判断是否可以提交；
 * - level / percent：三条硬性要求都满足后才按熵估算给出低 / 中 / 高。
 */
export function usePasswordStrength(passwordRef) {
  const touched = ref(false)
  const hardRules = computed(() => analyzePassword(passwordRef.value))
  const rules = computed(() => {
    const list = hardRules.value.map((rule) => ({
      ...rule,
      state: rule.ok ? 'ok' : (touched.value ? 'error' : 'idle'),
    }))
    const special = hasSpecialCharacter(passwordRef.value)
    list.push({ key: 'special', optional: true, ok: special, state: special ? 'ok' : 'idle' })
    return list
  })
  const level = computed(() => getPasswordStrengthLevel(passwordRef.value || '', hardRules.value))
  const percent = computed(() => (level.value ? STRENGTH_PERCENT[level.value] : 0))

  function touch() {
    touched.value = true
  }

  return { touched, rules, hardRules, level, percent, touch }
}

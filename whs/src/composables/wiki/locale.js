/**
 * 维基语言状态。
 *
 * - 界面文案走 vue-i18n（与全站一致，固定文案硬编码在 zh.json / en.json）；
 * - 页面内容 / 标题等动态内容不能硬编码：切换语言时，维基页面 watch 本模块
 *   暴露的 lang（即 vue-i18n locale），向后端发送对应语言的请求实时取回内容。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

// 语言显示名（页面内语言切换器使用）
export const LANG_LABELS = { zh: '中文', en: 'English' }

export function useWikiLocale() {
  const { locale } = useI18n()
  const lang = computed(() => (locale.value === 'en' ? 'en' : 'zh'))
  return { lang }
}

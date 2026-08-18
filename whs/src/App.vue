<script setup>
import { watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Tips from './components/tips.vue'
import { useAuth } from './composables/useAuth'
import { useSiteConfig } from './composables/useSiteConfig'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const { state: authState, fetchMe } = useAuth()
// 站点公开配置（title_suffix / hcaptcha_site_key / 301 等），与路由守卫共用同一份
const siteConfig = useSiteConfig()

// 全局快捷键：同时按下 G + D 回到首页
const pressedKeys = new Set()

function handleShortcutKeydown(e) {
  if (e.repeat) return
  pressedKeys.add(e.code)
  if (pressedKeys.has('KeyG') && pressedKeys.has('KeyD')) {
    pressedKeys.clear()
    router.push('/')
  }
}

function handleShortcutKeyup(e) {
  pressedKeys.delete(e.code)
}

onMounted(() => {
  // 统一在此拉取一次用户信息（已登录时）：各页面/组件不再各自调用 fetchMe，
  // 避免访问同一页面时（如首页 + 导航栏）重复请求后端。
  // 之后每次用户信息变更（登录/注册/改资料/改头像/改邮箱/改密码/考试通过等）
  // 由对应操作在成功后调用 fetchMe() 刷新公共 user 数据。
  if (authState.token) fetchMe()

  window.addEventListener('keydown', handleShortcutKeydown)
  window.addEventListener('keyup', handleShortcutKeyup)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleShortcutKeydown)
  window.removeEventListener('keyup', handleShortcutKeyup)
})

watch([() => route.meta.titleKey, locale, () => siteConfig.value?.title_suffix], () => {
  const key = route.meta.titleKey || 'pageTitle.home'
  const base = t(key)
  const suffix = (siteConfig.value?.title_suffix || {})[locale.value] || ''
  if (key === 'pageTitle.home' && suffix) {
    document.title = base + suffix
  } else {
    document.title = base
  }
}, { immediate: true })
</script>

<template>
  <router-view />
  <Tips />
</template>

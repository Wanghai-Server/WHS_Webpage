<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Tips from './components/tips.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const titleSuffix = ref({ zh: '', en: '' })

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

onMounted(async () => {
  try {
    const res = await fetch('/api/whs')
    const data = await res.json()
    if (data.title_suffix) {
      titleSuffix.value = data.title_suffix
    }
  } catch {
    console.error('Failed to fetch title suffix')
  }

  window.addEventListener('keydown', handleShortcutKeydown)
  window.addEventListener('keyup', handleShortcutKeyup)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleShortcutKeydown)
  window.removeEventListener('keyup', handleShortcutKeyup)
})

watch([() => route.meta.titleKey, locale, titleSuffix], () => {
  const key = route.meta.titleKey || 'pageTitle.home'
  const base = t(key)
  const suffix = titleSuffix.value[locale.value] || ''
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

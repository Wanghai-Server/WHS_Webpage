<script setup>
/**
 * 页面不存在空态：展示缺失的 slug，管理员可一键进入编辑器创建。
 */
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { FileQuestion, Plus } from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'

const props = defineProps({
  slug: { type: String, default: '' },
})

const router = useRouter()
const { t } = useI18n()
const { state: authState } = useAuth()

const canWrite = !!authState.user && (authState.user.permission || 0) >= 3

function createPage() {
  router.push({ path: '/wiki/edit', query: props.slug ? { slug: props.slug } : {} })
}
</script>

<template>
  <div class="wiki-404 load-in">
    <FileQuestion :size="44" class="icon" />
    <h2 class="title">{{ t('pages.wiki.notFound.title') }}</h2>
    <p class="desc">{{ t('pages.wiki.notFound.desc') }}</p>
    <code v-if="slug" class="slug">{{ slug }}</code>
    <button v-if="canWrite" type="button" class="create-btn" @click="createPage">
      <Plus :size="16" />
      {{ t('pages.wiki.notFound.create') }}
    </button>
  </div>
</template>

<style scoped>
.wiki-404 {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 55vh;
  text-align: center;
  padding: 48px 24px;
}

.icon {
  color: var(--links-color);
  margin-bottom: 16px;
}

.title {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 800;
  color: var(--text-color);
}

.desc {
  margin: 0 0 12px;
  font-size: 14.5px;
  color: var(--links-color);
}

.slug {
  display: inline-block;
  margin-bottom: 20px;
  padding: 4px 12px;
  border-radius: 8px;
  background: var(--float-bg);
  font-size: 13px;
  color: var(--text-color);
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border: 1px dashed var(--notice-color);
  border-radius: 999px;
  background: transparent;
  color: var(--text-color);
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.create-btn:hover {
  background: var(--float-bg);
}
</style>

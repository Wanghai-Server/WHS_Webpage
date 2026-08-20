<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'

const props = defineProps({
  user: { type: Object, required: true },
})

const { t } = useI18n()

// html: false —— 源文本中的 HTML 会被转义，防止 XSS；linkify/breaks 提升阅读体验
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const renderedProfile = computed(() => md.render(props.user.profile || ''))

const genderLabel = computed(() => {
  if (props.user.gender === 'male') return t('user.male')
  if (props.user.gender === 'female') return t('user.female')
  return null
})

const birthdayLabel = computed(() => {
  const y = props.user.birthday_year
  const m = props.user.birthday_month
  const d = props.user.birthday_day
  if (!y) return null
  if (m) {
    if (d) return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    return `${y}-${String(m).padStart(2, '0')}`
  }
  return String(y)
})
</script>

<template>
  <section class="user-profile">
    <!-- 顶部：生日 / 性别等扩展信息 -->
    <div class="profile-facts">
      <div class="fact load-in">
        <span class="fact-label">{{ t('user.birthday') }}</span>
        <span class="fact-value">{{ birthdayLabel || t('user.noBirthday') }}</span>
      </div>
      <div class="fact load-in" style="--load-delay: 80ms">
        <span class="fact-label">{{ t('user.gender') }}</span>
        <span class="fact-value">{{ genderLabel || t('user.none') }}</span>
      </div>
    </div>

    <!-- 真正的个人简介（Markdown 渲染） -->
    <div class="profile-body load-in" style="--load-delay: 160ms">
      <div v-if="props.user.profile" class="markdown" v-html="renderedProfile"></div>
      <p v-else class="empty">{{ t('user.noProfile') }}</p>
    </div>
  </section>
</template>

<style scoped>
.user-profile {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.profile-facts {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.fact {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-radius: 12px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
}

.fact-label {
  color: var(--links-color);
  font-size: 13px;
}

.fact-value {
  color: var(--text-color);
  font-size: 14px;
  font-weight: 600;
}

.profile-body {
  padding: 24px 28px;
  border-radius: 20px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  min-height: 120px;
}

.empty {
  margin: 0;
  color: var(--links-color);
  text-align: center;
  padding: 32px 0;
}

/* Markdown 渲染样式（适配主题） */
.markdown {
  color: var(--text-color);
  line-height: 1.7;
  word-break: break-word;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3) {
  margin: 1.2em 0 0.6em;
  line-height: 1.3;
}

.markdown :deep(h1:first-child),
.markdown :deep(h2:first-child),
.markdown :deep(h3:first-child),
.markdown :deep(p:first-child) {
  margin-top: 0;
}

.markdown :deep(p) {
  margin: 0.6em 0;
}

.markdown :deep(a) {
  color: var(--links-color);
  text-decoration: none;
}

.markdown :deep(code) {
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--btn-hover);
  font-family: monospace;
}

.markdown :deep(pre) {
  padding: 12px;
  border-radius: 10px;
  background: var(--btn-hover);
  overflow-x: auto;
}

.markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown :deep(blockquote) {
  margin: 0.8em 0;
  padding-left: 14px;
  border-left: 3px solid var(--links-color);
  color: var(--links-color);
}

.markdown :deep(img) {
  max-width: 100%;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  padding-left: 1.5em;
}
</style>

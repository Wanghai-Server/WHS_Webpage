<script setup>
import { useI18n } from 'vue-i18n'
import Top_navbar from '../../components/top_navbar.vue'
import Page_footer from '../../components/page_footer.vue'

const { t } = useI18n()
</script>

<template>
  <Top_navbar />

  <main class="wiki-hero">
    <div class="wiki-inner load-in">
      <h1 class="wiki-title">{{ t('pages.wiki.title') }}</h1>
      <p class="wiki-subtitle">{{ t('pages.wiki.description') }}</p>
    </div>
  </main>

  <Page_footer />
</template>

<style scoped>
.wiki-hero {
  min-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 120px 24px 60px;
  box-sizing: border-box;
}

.wiki-inner {
  max-width: 640px;
  text-align: center;
}

.wiki-title {
  margin: 0 0 20px;
  font-size: 44px;
  font-weight: 800;
  color: var(--text-color);
}

.wiki-subtitle {
  margin: 0;
  font-size: 18px;
  line-height: 1.7;
  color: var(--links-color);
}

@media (max-width: 768px) {
  .wiki-title {
    font-size: 32px;
  }

  .wiki-subtitle {
    font-size: 16px;
  }
}
</style>

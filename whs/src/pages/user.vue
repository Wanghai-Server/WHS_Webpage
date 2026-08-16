<script setup>
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'

const route = useRoute()
const { t } = useI18n()
</script>

<template>
  <Top_navbar />

  <main class="placeholder">
    <h1>{{ t('pageTitle.user') }}</h1>
    <p>UID: {{ route.params.uid }}</p>
  </main>

  <Page_footer />
</template>

<style scoped>
.placeholder {
  min-height: 60vh;
  padding-top: 120px;
  text-align: center;
  color: var(--text-color);
}
</style>

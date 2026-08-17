<script setup>
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

const router = useRouter()
const { t } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

function startExam() {
  if (!authState.token) {
    showTip('warning', t('user.notLoggedIn'))
    router.push('/login')
    return
  }
  router.push('/joinus/exam')
}
</script>

<template>
  <Top_navbar />

  <main class="joinus-hero">
    <div class="joinus-inner load-in">
      <h1 class="joinus-title">{{ t('joinus.title') }}</h1>
      <p class="joinus-subtitle">{{ t('joinus.subtitle') }}</p>
      <button type="button" class="joinus-start" @click="startExam">
        {{ t('joinus.start') }}
      </button>
    </div>
  </main>

  <Page_footer />
</template>

<style scoped>
.joinus-hero {
  min-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 120px 24px 60px;
  box-sizing: border-box;
}

.joinus-inner {
  max-width: 640px;
  text-align: center;
}

.joinus-title {
  margin: 0 0 20px;
  font-size: 44px;
  font-weight: 800;
  color: var(--text-color);
}

.joinus-subtitle {
  margin: 0 0 36px;
  font-size: 18px;
  line-height: 1.7;
  color: var(--links-color);
}

.joinus-start {
  padding: 14px 44px;
  border: none;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-size: 18px;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.joinus-start:hover {
  background: #d99a1f;
}

@media (max-width: 768px) {
  .joinus-title {
    font-size: 32px;
  }

  .joinus-subtitle {
    font-size: 16px;
  }
}
</style>

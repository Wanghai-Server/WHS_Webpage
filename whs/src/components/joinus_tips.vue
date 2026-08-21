<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight } from 'lucide-vue-next'

// 可复用的「加入我们」引导组件：四步流程 + 开始答题按钮。
// 文案来自顶层 join.* 词条（zh/en），使用方无需传参。
const { t, tm } = useI18n()
const router = useRouter()
// tm() 不具响应性：用 computed 包裹，语言切换时跟随翻译（模板自动解包）
const joinSteps = computed(() => tm('join.steps'))
</script>

<template>
  <section class="section join-section">
    <div class="join-panel">
      <div class="section-head">
        <span class="head-bar"></span>
        <h2>{{ t('join.title') }}</h2>
      </div>

      <div class="join-steps">
        <div v-for="(step, i) in joinSteps" :key="i" class="join-step">
          <span class="join-num">{{ i + 1 }}</span>
          <div>
            <h3>{{ step.title }}</h3>
            <p>{{ step.desc }}</p>
          </div>
        </div>
      </div>

      <button type="button" class="gold-btn big" @click="router.push('/joinus')">
        {{ t('join.button') }}
        <ChevronRight :size="20" />
      </button>
      <p class="join-hint">{{ t('join.hint') }}</p>
    </div>
  </section>
</template>

<style scoped>
.section {
  max-width: 1100px;
  margin: 0 auto;
  padding: 96px 24px;
  box-sizing: border-box;
}

.join-section {
  padding-bottom: 120px;
}

.section-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin-bottom: 40px;
}

.head-bar {
  width: 44px;
  height: 5px;
  border-radius: 999px;
  background: #ebaa28;
  margin-bottom: 18px;
}

.section-head h2 {
  margin: 0;
  font-size: 32px;
  font-weight: 800;
  color: var(--text-color);
}

.join-panel {
  text-align: center;
  background: linear-gradient(135deg, rgba(235, 170, 40, 0.09), rgba(235, 170, 40, 0.02));
  border: 1px solid rgba(235, 170, 40, 0.28);
  border-radius: 24px;
  padding: 48px 32px 44px;
}

.join-steps {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  margin-bottom: 40px;
  text-align: left;
}

.join-step {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.join-num {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.join-step h3 {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-color);
}

.join-step p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--links-color);
}

.gold-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 40px;
  border: none;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-size: 17px;
  font-weight: 700;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    transform 0.2s ease;
}

.gold-btn:hover {
  background: #d99a1f;
  transform: translateY(-1px);
}

.join-hint {
  margin: 16px 0 0;
  font-size: 13px;
  color: var(--links-color);
}

@media (max-width: 768px) {
  .section {
    padding: 72px 20px;
  }

  .section-head h2 {
    font-size: 26px;
  }

  .join-steps {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .join-steps {
    grid-template-columns: 1fr;
  }
}
</style>

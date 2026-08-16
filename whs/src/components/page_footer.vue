<script setup>
import { ref, computed, onMounted } from 'vue'
import { Sun, Moon, Monitor, Github } from 'lucide-vue-next'

import { useLanguage } from '../composables/useLanguage'

const { t, locale, switchLanguage } = useLanguage()

// 主题状态：'light'（亮色）| 'system'（跟随系统）| 'dark'（暗色）
const theme = ref('system')

const langIndex = computed(() => (locale.value === 'zh' ? 0 : 1))
const themeIndex = computed(() => ['light', 'system', 'dark'].indexOf(theme.value))

function applyTheme(mode) {
  const html = document.documentElement
  html.classList.remove('light', 'dark')
  if (mode === 'light') {
    html.classList.add('light')
  } else if (mode === 'dark') {
    html.classList.add('dark')
  }
  theme.value = mode
  localStorage.setItem('theme', mode)
}

// 点击语言开关任意位置：在中/英之间切换
function toggleLanguage() {
  switchLanguage(locale.value === 'zh' ? 'en' : 'zh')
}

onMounted(() => {
  // 只在页面重载时计算一次：仅当保存的是具体主题（light/dark）才恢复，否则保持默认「跟随系统」
  const saved = localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') {
    applyTheme(saved)
  }
})
</script>

<template>
  <footer class="footer">
    <div class="footer-inner">
      <!-- 第一行 -->
      <div class="footer-top">
        <!-- 左：LOGO + 名称 + 描述 -->
        <div class="footer-brand">
          <RouterLink to="/" class="brand-logo">
            <img src="/icons.png" alt="WHS" />
            <span class="brand-name">{{ t('nav.title') }}</span>
          </RouterLink>
          <p class="brand-desc">{{ t('pages.home.description') }}</p>
        </div>

        <!-- 中：快速链接 -->
        <div class="footer-links">
          <h3 class="footer-title">{{ t('footer.quick_links') }}</h3>
          <ul class="quick-links">
            <li>
              <RouterLink to="/news">{{ t('nav.news') }}</RouterLink>
              <!-- 附属内容（暂无） -->
            </li>
            <li>
              <RouterLink to="/about">{{ t('nav.about') }}</RouterLink>
              <!-- 附属内容（暂无） -->
            </li>
          </ul>
        </div>

        <!-- 右：语言切换 + 主题切换 -->
        <div class="footer-switches">
          <!-- 语言切换：整体可点击，点任意位置切换 -->
          <button class="switch lang-switch" type="button" :aria-label="t('footer.language')" @click="toggleLanguage">
            <span class="switch-thumb" :style="{ transform: `translateX(${langIndex * 100}%)` }"></span>
            <span class="lang-option" :class="{ active: locale === 'zh' }">中文</span>
            <span class="lang-option" :class="{ active: locale === 'en' }">EN</span>
          </button>

          <!-- 主题切换 -->
          <div class="switch theme-switch" role="group" :aria-label="t('footer.theme')">
            <span class="switch-thumb" :style="{ transform: `translateX(${themeIndex * 100}%)` }"></span>
            <button
              :class="{ active: theme === 'light' }"
              :aria-label="t('footer.theme_light')"
              :title="t('footer.theme_light')"
              @click="applyTheme('light')"
            >
              <Sun :size="18" />
            </button>
            <button
              :class="{ active: theme === 'system' }"
              :aria-label="t('footer.theme_system')"
              :title="t('footer.theme_system')"
              @click="applyTheme('system')"
            >
              <Monitor :size="18" />
            </button>
            <button
              :class="{ active: theme === 'dark' }"
              :aria-label="t('footer.theme_dark')"
              :title="t('footer.theme_dark')"
              @click="applyTheme('dark')"
            >
              <Moon :size="18" />
            </button>
          </div>
        </div>
      </div>

      <!-- 第二行 -->
      <div class="footer-bottom">
        <a
          class="copyright"
          href="https://github.com/Wanghai-Server/WHS_Webpage?tab=MIT-1-ov-file"
          target="_blank"
          rel="noopener noreferrer"
        >
          MIT License, Copyright (c) 2026 WangHai Server
        </a>
        <a
          class="github-link"
          href="https://github.com/Wanghai-Server/WHS_Webpage"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="GitHub"
        >
          <Github :size="20" />
        </a>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.footer {
  border-top: 2px solid var(--text-color);
  background: var(--navbar-bg);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  padding: 40px 60px 24px;
}

.footer-inner {
  max-width: 1100px;
  margin: 0 auto;
}

.footer-top {
  display: grid;
  grid-template-columns: 2fr 1fr auto;
  gap: 48px;
  align-items: start;
}

/* 品牌区 */
.brand-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-color);
  text-decoration: none;
}

.brand-logo img {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.brand-name {
  font-size: 24px;
  font-weight: 700;
}

.brand-desc {
  margin: 16px 0 0;
  max-width: 360px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--links-color);
}

/* 快速链接 */
.footer-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}

.quick-links {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quick-links a {
  color: var(--links-color);
  text-decoration: none;
  font-size: 15px;
  transition: color 0.2s ease;
}

.quick-links a:hover {
  color: var(--text-color);
}

/* 切换器容器 */
.footer-switches {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: flex-start;
}

/* 分段式滑动开关 */
.switch {
  position: relative;
  display: inline-flex;
  padding: 4px;
  border-radius: 999px;
  background: var(--btn-hover);
}

.switch-thumb {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 4px;
  border-radius: 999px;
  background: var(--card-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  transition: transform 0.3s ease;
}

/* 语言切换：整体可点击，点任意位置切换 */
.lang-switch {
  border: none;
  cursor: pointer;
  font: inherit;
}

.lang-switch .switch-thumb {
  width: 72px;
}

.lang-option {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 36px;
  font-size: 14px;
  white-space: nowrap;
  color: var(--links-color);
  transition: color 0.2s ease;
}

.lang-option.active {
  color: var(--text-color);
}

/* 主题切换：三个选项 */
.theme-switch .switch-thumb {
  width: 48px;
}

.theme-switch button {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 36px;
  border: none;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: color 0.2s ease;
}

.theme-switch button.active {
  color: var(--text-color);
}

/* 第二行 */
.footer-bottom {
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid var(--links-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.copyright {
  color: var(--links-color);
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s ease;
}

.copyright:hover {
  color: var(--text-color);
}

.github-link {
  display: inline-flex;
  color: var(--links-color);
  transition: color 0.2s ease;
}

.github-link:hover {
  color: var(--text-color);
}

/* 移动端 */
@media (max-width: 768px) {
  .footer {
    padding: 32px 20px 20px;
  }

  .footer-top {
    grid-template-columns: 1fr;
    gap: 32px;
  }

  .footer-switches {
    align-items: stretch;
  }

  .footer-bottom {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>

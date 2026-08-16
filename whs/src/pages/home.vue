<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'

import defaultBg from '../assets/background.png'

const { t } = useI18n()
const router = useRouter()

const bgImage = ref(defaultBg)

onMounted(() => {
  // 从现有图片中随机抽取一张作为 hero 背景（每次刷新随机）
  const modules = import.meta.glob('../assets/wanghai_web/*.png', { eager: true })
  const wanghaiImages = Object.values(modules).map((m) => m.default)
  const allImages = [defaultBg, ...wanghaiImages]
  bgImage.value = allImages[Math.floor(Math.random() * allImages.length)]
})

// 引导用户前往登录/注册页（暂不实现登录/注册逻辑）
function goLogin() {
  router.push('/login')
}
</script>

<template>
    <Top_navbar />

    <section class="hero" :style="{ backgroundImage: `url(${bgImage})` }">
        <div class="hero-overlay">
            <h1>{{ t('pages.home.title') }}</h1>
            <p>{{ t('pages.home.description') }}</p>
            <form class="signup" novalidate @submit.prevent="goLogin">
                <input type="email" :placeholder="t('pages.home.email_placeholder')" />
                <button type="submit">{{ t('pages.home.signup') }}</button>
            </form>
        </div>
    </section>

    <div class="home"></div>
    <Page_footer />
</template>

<style scoped>
.hero {
  position: relative;
  width: 100%;
  height: 100vh;
  background-size: cover;
  background-repeat: no-repeat;
  background-position: center;
}

.hero-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 0 24px;
  box-sizing: border-box;

  /* 深色半透明覆盖层（参考旧版 rgba(0,0,0,0.4)，加深并提高不透明度） */
  background: rgba(0, 0, 0, 0.55);
}

.hero-overlay h1 {
  margin: 0 0 16px;
  font-size: 56px;
  font-weight: 800;
  color: #ffffff;
}

.hero-overlay p {
  margin: 0 0 32px;
  max-width: 720px;
  font-size: 20px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.9);
}

.signup {
  display: flex;
  align-items: stretch;
  width: 100%;
  max-width: 480px;
}

.signup input {
  flex: 1;
  min-width: 0;
  padding: 14px 20px;
  font-size: 16px;
  border: 1px solid rgba(17, 24, 39, 0.15);
  border-right: none;
  border-radius: 999px 0 0 999px;
  background: #ffffff;
  color: #333333;
  outline: none;
}

.signup input::placeholder {
  color: #9aa3af;
}

.signup button {
  padding: 14px 28px;
  font-size: 16px;
  font-weight: 600;
  border: none;
  border-radius: 0 999px 999px 0;
  background: #ebaa28;
  color: #1f2937;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.2s ease;
}

.signup button:hover {
  background: #d99a1f;
}

@media (max-width: 768px) {
  .hero-overlay h1 {
    font-size: 36px;
  }

  .hero-overlay p {
    font-size: 16px;
  }
}
</style>

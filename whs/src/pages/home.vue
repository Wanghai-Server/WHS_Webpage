<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import RegisterForm from '../components/register.vue'

import { useAuth } from '../composables/useAuth'

const { t } = useI18n()
const router = useRouter()

const bgImage = ref('')      // 懒加载：初始为空，图片加载完成后再填充
const bgLoaded = ref(false)  // 背景是否加载完成（用于淡入）

const email = ref('')
const showRegister = ref(false)

const { state } = useAuth()
const isLoggedIn = computed(() => !!state.token)
const user = computed(() => state.user)
const username = computed(() => user.value?.username || 'User')
const fullname = computed(() => user.value?.fullname || '')

// 正式成员判定：权限等级 >= 2（player）即视为已完成入服考试、成为正式成员。
// 登录响应与 /api/user/me 均返回 permission 字段，无需额外请求即可判断。
const isMember = computed(() => (user.value?.permission ?? 0) >= 2)

function goExam() {
  router.push('/joinus/exam')
}

function onSignup() {
  showRegister.value = true
}

function handleKeydown(event) {
  if (event.key === 'Escape' && showRegister.value) {
    showRegister.value = false
  }
}

onMounted(() => {
  // 懒加载 hero 背景：随机抽取一张后按需动态导入，不再 eager 一次性解析全部大图
  const modules = import.meta.glob([
    '../assets/background.png',
    '../assets/wanghai_web/*.png'
  ])
  const keys = Object.keys(modules)
  if (keys.length) {
    const key = keys[Math.floor(Math.random() * keys.length)]
    modules[key]().then((mod) => {
      const url = mod.default
      const img = new Image()
      img.onload = () => {
        bgImage.value = url
        bgLoaded.value = true
      }
      img.src = url
    })
  }

  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
    <Top_navbar />

    <section class="hero">
        <div
          class="hero-bg"
          :class="{ loaded: bgLoaded }"
          :style="bgImage ? { backgroundImage: `url(${bgImage})` } : {}"
        ></div>
        <div class="hero-overlay">
            <h1>{{ t('pages.home.title') }}</h1>
            <p>{{ t('pages.home.description') }}</p>
            <form v-if="!isLoggedIn" class="signup" novalidate @submit.prevent="onSignup">
                <input v-model="email" type="email" :placeholder="t('pages.home.email_placeholder')" />
                <button type="submit">{{ t('pages.home.signup') }}</button>
            </form>
            <button v-else-if="!isMember" type="button" class="member-cta" @click="goExam">
                {{ t('pages.home.become_member') }}
            </button>
            <p v-else class="welcome">{{ t('pages.home.welcome', { name: fullname || username }) }}</p>
        </div>
    </section>

    <!-- 注册弹窗：复用 register.vue 并注入 email -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showRegister" class="modal-overlay" @click.self="showRegister = false">
          <div class="modal">
            <RegisterForm :prefill="{ email }" @switch-login="showRegister = false" />
          </div>
        </div>
      </Transition>
    </Teleport>

    <div class="home"></div>
    <Page_footer />
</template>

<style scoped>
.hero {
  position: relative;
  width: 100%;
  min-height: 100vh;
  background-color: var(--bg-color); /* 图片懒加载完成前的占位底色 */
}

/* 懒加载背景层：先透明，图片加载完成后淡入 */
.hero-bg {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-repeat: no-repeat;
  background-position: center;
  opacity: 0;
  transition: opacity 0.6s ease;
}

.hero-bg.loaded {
  opacity: 1;
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

/* 已登录但未成为正式成员：引导参加入服考试。
   与上方"输入框 + 注册按钮"组合等宽（.signup 为 max-width: 480px 的 flex） */
.member-cta {
  display: block;
  width: 100%;
  max-width: 480px;
  padding: 14px 28px;
  border: none;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-size: 16px;
  font-weight: 600;
  text-align: center;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.2s ease;
}

.member-cta:hover {
  background: #d99a1f;
}

/* 已登录时的欢迎语 */
.welcome {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  color: #ffffff;
}

/* 注册弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.modal {
  position: relative;
  max-height: 90vh;
  overflow-y: auto;
  border-radius: 20px;
}

/* 弹窗内复用组件：去掉其自带的大顶部外边距，避免顶部留白 */
.modal :deep(.register-form) {
  margin: 0 auto 40px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
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

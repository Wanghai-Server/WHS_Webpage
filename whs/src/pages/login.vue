<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LoginForm from '../components/login.vue'
import RegisterForm from '../components/register.vue'
import Page_footer from '../components/page_footer.vue'
import { useAuth } from '../composables/useAuth'

// 登录页本身不带顶部导航栏，只有底部导航栏
const mode = ref('login') // 'login' | 'register'
const prefill = ref({})

const router = useRouter()
const { state: authState, fetchMe } = useAuth()

// 已登录用户再访问 /login：先向后端校验 token，有效则直接跳转到用户页面（SPA 内 replace，等价 301）
onMounted(async () => {
  if (!authState.token) return
  const user = await fetchMe()
  if (user?.uid) {
    router.replace(`/user/${user.uid}`)
  }
})

function onSwitchRegister(data) {
  prefill.value = data || {}
  mode.value = 'register'
}

function onSwitchLogin() {
  mode.value = 'login'
}
</script>

<template>
  <main class="auth-page">
    <LoginForm v-if="mode === 'login'" @switch-register="onSwitchRegister" />
    <RegisterForm v-else :prefill="prefill" @switch-login="onSwitchLogin" />
  </main>

  <Page_footer />
</template>

<style scoped>
.auth-page {
  min-height: calc(100vh - 200px);
}
</style>

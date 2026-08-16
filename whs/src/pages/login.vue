<script setup>
import { ref } from 'vue'
import LoginForm from '../components/login.vue'
import RegisterForm from '../components/register.vue'
import Page_footer from '../components/page_footer.vue'

// 登录页本身不带顶部导航栏，只有底部导航栏
const mode = ref('login') // 'login' | 'register'
const prefill = ref({})

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

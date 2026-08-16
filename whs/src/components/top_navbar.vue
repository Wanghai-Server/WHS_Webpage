<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { animate, stagger } from 'animejs'
import { User, Mail, X, ArrowLeft } from 'lucide-vue-next'
import MessageBox from './message_box.vue'
import { useAuth } from '../composables/useAuth'

const props = defineProps({
  backRoute: { type: String, default: '' },
  navRoutes: { type: Object, default: null },
})

const { t } = useI18n()
const router = useRouter()
const { state: authState, fetchMe } = useAuth()

// 登录态与头像
const isLoggedIn = computed(() => !!authState.token)
const avatarSrc = computed(() => (authState.user && authState.user.avatar ? `/api/user/${authState.user.uid}/avatar` : ''))
const userLink = computed(() => (authState.user ? `/user/${authState.user.uid}` : '/login'))

// 导航链接：默认 /news + /about，可被 navRoutes 覆盖
const links = computed(() => {
  if (props.navRoutes) {
    return Object.entries(props.navRoutes).map(([key, route]) => ({ key, route }))
  }
  return [
    { key: 'nav.news', route: '/news' },
    { key: 'nav.about', route: '/about' },
  ]
})

function goBack() {
  if (props.backRoute) {
    router.push(props.backRoute)
  } else {
    router.back()
  }
}

// 导航栏高度（px），与下方 <style> 中的 height 保持一致，用于计算滚动阈值
const NAVBAR_HEIGHT = 48
// 与 <style> 中 @media (max-width: 768px) 保持一致
const MOBILE_BREAKPOINT = 768

const scrolled = ref(window.scrollY > NAVBAR_HEIGHT * 1.5)
const menuOpen = ref(false)
const navbarRef = ref(null)
const showMessages = ref(false)
const messageBoxRef = ref(null)

// 点击消息图标：关闭时打开，打开时（图标变为叉）关闭
function toggleMessages() {
  if (showMessages.value) {
    messageBoxRef.value?.close()
  } else {
    showMessages.value = true
  }
}
let isMobile = false
let mediaQuery = null
let ready = false
let loginBtnNaturalWidth = 0

function handleScroll() {
  const nowScrolled = window.scrollY > NAVBAR_HEIGHT * 1.5
  if (nowScrolled !== scrolled.value) {
    scrolled.value = nowScrolled
    if (ready) {
      animateLoginTransition(nowScrolled)
    } else {
      setLoginState(nowScrolled)
    }
  }
}

// 直接设置登录按钮的脱离/吸附状态（不播放动画，用于初始化）
function setLoginState(isScrolled) {
  const root = navbarRef.value
  if (!root) return
  const btn = root.querySelector('.login-btn')
  const fab = root.querySelector('.user-fab')
  if (!btn || !fab) return

  if (isScrolled) {
    loginBtnNaturalWidth = btn.offsetWidth
    btn.style.pointerEvents = 'none'
    btn.style.opacity = '0'
    btn.style.width = '0px'
    btn.style.marginLeft = '0px'
    fab.style.pointerEvents = 'auto'
    fab.style.opacity = '1'
  } else {
    btn.style.pointerEvents = 'auto'
    btn.style.opacity = '1'
    btn.style.width = ''
    btn.style.marginLeft = ''
    fab.style.pointerEvents = 'none'
    fab.style.opacity = '0'
  }
}

// 登录按钮的脱离/吸附动画（带弹性，像被胶水黏住一样）
function animateLoginTransition(isScrolled) {
  const root = navbarRef.value
  if (!root) return
  const btn = root.querySelector('.login-btn')
  const fab = root.querySelector('.user-fab')
  if (!btn || !fab) return

  if (isScrolled) {
    // 脱离：文字按钮淡出并收起（宽度/间距归零），圆形带弹性弹出
    btn.style.pointerEvents = 'none'
    fab.style.pointerEvents = 'auto'
    loginBtnNaturalWidth = btn.offsetWidth
    animate(btn, { opacity: 0, width: 0, marginLeft: 0, duration: 250, ease: 'outQuad' })
    animate(fab, { opacity: [0, 1], scale: [0.5, 1], duration: 500, ease: 'outBack' })
  } else {
    // 吸附：文字按钮展开并回弹，圆形淡出
    btn.style.pointerEvents = 'auto'
    fab.style.pointerEvents = 'none'
    animate(btn, { opacity: 1, width: loginBtnNaturalWidth, marginLeft: 28, duration: 300, ease: 'outQuad' })
    animate(fab, { opacity: [1, 0], scale: [1, 0.5], duration: 180, ease: 'outQuad' })
  }
}

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function closeMenu() {
  menuOpen.value = false
}

function handleClickOutside(event) {
  if (navbarRef.value && !navbarRef.value.contains(event.target)) {
    closeMenu()
  }
}

// 断点切换动画：对「刚出现」的元素做淡入 + 下滑
function animateBreakpointSwitch() {
  const root = navbarRef.value
  if (!root) return

  const itemsSelector = isMobile
    ? '.menu-toggle, .login-mobile'
    : scrolled.value
      ? '.logo-text, .links a'
      : '.logo-text, .links a, .login-btn'

  animate(root.querySelectorAll(itemsSelector), {
    opacity: [0, 1],
    translateY: [-8, 0],
    duration: 250,
    delay: stagger(50),
    ease: 'outQuad'
  })
}

// 跨越 768px 断点时触发：更新状态、收起菜单、播放切换动画
function onMediaChange(event) {
  const nowMobile = event.matches
  if (nowMobile === isMobile) return
  isMobile = nowMobile
  if (!nowMobile) closeMenu()
  // 等下一帧布局/样式生效后再处理，确保目标元素已可见
  requestAnimationFrame(() => {
    // 先重置登录按钮状态，清除跨断点时残留的内联样式（如 width:0 / opacity:0）
    setLoginState(scrolled.value)
    // 再播放断点切换动画
    animateBreakpointSwitch()
  })
}

// 入场动画：容器淡入 + 所有子元素交错淡入下滑（参考旧版使用 anime.js）
function playEntranceAnimation() {
  if (!navbarRef.value) return

  // 根据当前断点只选取可见元素，保证交错节奏整齐
  const itemsSelector = isMobile
    ? '.menu-toggle, .logo, .login-mobile'
    : scrolled.value
      ? '.logo, .links a'
      : '.logo, .links a, .login-btn'

  // 导航栏容器整体淡入
  animate(navbarRef.value, {
    opacity: [0, 1],
    duration: 400,
    ease: 'outQuad'
  })

  // 各子元素依次淡入 + 下滑
  animate(navbarRef.value.querySelectorAll(itemsSelector), {
    opacity: [0, 1],
    translateY: [-16, 0],
    duration: 600,
    delay: stagger(70),
    ease: 'outQuad'
  })
}

onMounted(() => {
  if (isLoggedIn.value) fetchMe()
  handleScroll() // 初始化滚动状态与登录按钮状态（不播放动画）
  ready = true

  window.addEventListener('scroll', handleScroll, { passive: true })
  document.addEventListener('click', handleClickOutside)

  // 监听 768px 断点，跨越时触发切换动画
  mediaQuery = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`)
  isMobile = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange)

  playEntranceAnimation()
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
  document.removeEventListener('click', handleClickOutside)
  if (mediaQuery) {
    mediaQuery.removeEventListener('change', onMediaChange)
  }
})
</script>

<template>
  <header class="navbar" :class="{ scrolled }" ref="navbarRef">
    <!-- 移动端左侧：折叠按钮（桌面端隐藏） -->
    <button class="menu-toggle" :aria-label="t('nav.menu')" @click="toggleMenu">
      <span>{{ menuOpen ? '✕' : '☰' }}</span>
    </button>

    <!-- 中间：LOGO（移动端只显示图标） -->
    <RouterLink to="/" class="logo">
      <img src="/icons.png" alt="WHS" />
      <span class="logo-text">{{ t('nav.title') }}</span>
    </RouterLink>

    <!-- 桌面端右侧：导航链接 + 登录按钮 -->
    <div class="nav-right">
      <nav class="links">
        <RouterLink v-for="l in links" :key="l.route" :to="l.route">{{ t(l.key) }}</RouterLink>
      </nav>
      <RouterLink :to="userLink" class="login-btn">
        <template v-if="isLoggedIn">
          <img v-if="avatarSrc" :src="avatarSrc" class="avatar-img" alt="avatar" />
          <User v-else :size="20" />
        </template>
        <template v-else>{{ t('nav.login') }}</template>
      </RouterLink>
    </div>

    <!-- 移动端右侧：登录后显示头像 -->
    <RouterLink :to="userLink" class="login-mobile">
      <template v-if="isLoggedIn">
        <img v-if="avatarSrc" :src="avatarSrc" class="avatar-img" alt="avatar" />
        <User v-else :size="20" />
      </template>
      <template v-else>{{ t('nav.login') }}</template>
    </RouterLink>

    <!-- 桌面端脱离后的圆形登录按钮 -->
    <RouterLink :to="userLink" class="user-fab" :aria-label="t('nav.login')">
      <img v-if="isLoggedIn && avatarSrc" :src="avatarSrc" class="avatar-img" alt="avatar" />
      <User v-else :size="22" />
    </RouterLink>

    <!-- 移动端折叠菜单：除登录/注册外的导航目标 -->
    <Transition name="slide">
      <nav v-if="menuOpen" class="mobile-menu">
        <RouterLink v-for="l in links" :key="l.route" :to="l.route" @click="closeMenu">{{ t(l.key) }}</RouterLink>
      </nav>
    </Transition>
  </header>

  <!-- 返回按钮：传入 backRoute 时显示 -->
  <button
    v-if="props.backRoute"
    class="back-fab"
    :class="{ scrolled }"
    :aria-label="t('nav.back')"
    @click="goBack"
  >
    <ArrowLeft :size="22" />
  </button>

  <!-- 消息图标：桌面端滚动后吸附到导航栏左侧；页首/移动端时在屏幕左下角 -->
  <button
    class="message-fab"
    :class="{ attached: scrolled }"
    :aria-label="t('message.title')"
    @click="toggleMessages"
  >
    <X v-if="showMessages" :size="22" />
    <Mail v-else :size="22" />
  </button>

  <!-- 消息弹窗 -->
  <MessageBox ref="messageBoxRef" v-if="showMessages" @close="showMessages = false" />
</template>

<style scoped>
.navbar {
  /* 布局：固定顶部居中，胶囊（两端全圆）形状 */
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;

  /* 细长尺寸：高度 48px，长度（宽度）较大 */
  height: 48px;
  width: min(1080px, 90%);
  border-radius: 999px;
  box-sizing: border-box;

  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;

  /* 顶部状态：完全透明 */
  background-color: transparent;
  border: 1px solid transparent;
  box-shadow: none;
  backdrop-filter: blur(0px);
  -webkit-backdrop-filter: blur(0px);

  transition:
    width 0.4s ease,
    background-color 0.4s ease,
    border-color 0.4s ease,
    box-shadow 0.4s ease,
    backdrop-filter 0.4s ease,
    -webkit-backdrop-filter 0.4s ease;
}

/* 脱离状态：半透明 + 毛玻璃，长度变短 */
.navbar.scrolled {
  width: min(720px, 72%);
  background-color: var(--navbar-bg);
  border-color: rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-color);
  text-decoration: none;
  font-size: 20px;
  font-weight: 700;
  white-space: nowrap;
}

.logo img {
  width: 30px;
  height: 30px;
  object-fit: contain;
}

/* 桌面端右侧：链接组 + 登录按钮 */
.nav-right {
  display: flex;
  align-items: center;
}

.links {
  display: flex;
  align-items: center;
  gap: 28px;
}

.links a {
  color: var(--links-color);
  text-decoration: none;
  font-size: 16px;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.links a:hover {
  color: var(--text-color);
}

.login-btn {
  /* 与左侧链接之间的间距；JS 脱离动画里的 marginLeft: 28 与此保持一致 */
  margin-left: 28px;
  overflow: hidden;
  color: var(--links-color);
  text-decoration: none;
  font-size: 16px;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.login-btn:hover {
  color: var(--text-color);
}

/* 桌面端脱离后的圆形登录按钮 */
.user-fab {
  position: absolute;
  top: 0;
  right: -60px; /* 48px 圆 + 12px 间距 */
  z-index: 1002;

  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 999px;

  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  color: var(--text-color);

  opacity: 0;
  pointer-events: none;
}

.user-fab:hover {
  color: var(--text-color);
}

/* 消息图标：页首/移动端在屏幕左下角，桌面端滚动后吸附到导航栏左侧 */
.message-fab {
  position: fixed;
  top: calc(100vh - 72px); /* 24px 下边距 + 48px 高度 */
  left: 24px;
  z-index: 4000;

  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 999px;

  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  color: var(--text-color);
  cursor: pointer;

  /* 位置过渡：平滑缓动、无过冲，稳稳吸附在导航栏左侧 */
  transition:
    top 0.5s cubic-bezier(0.22, 1, 0.36, 1),
    left 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}

.message-fab:hover {
  color: var(--text-color);
}

/* 桌面端滚动后：吸附到导航栏左侧（镜像右侧用户圆，12px 间距） */
.message-fab.attached {
  top: 16px;
  left: calc(50% - min(360px, 36%) - 60px);
}

/* 返回按钮：与消息/用户圆形按钮同风格，位置随吸附状态切换 */
.back-fab {
  position: fixed;
  top: 16px;
  left: calc(50% - min(540px, 45%) - 60px);
  z-index: 4000;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 999px;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  color: var(--text-color);
  cursor: pointer;
  transition: left 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}

.back-fab:hover {
  color: var(--text-color);
}

.back-fab.scrolled {
  left: calc(50% - min(360px, 36%) - 120px);
}

/* 头像图 */
.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 999px;
}

.login-btn .avatar-img,
.login-mobile .avatar-img {
  width: 24px;
  height: 24px;
  vertical-align: middle;
}

/* 移动端折叠按钮（桌面端隐藏） */
.menu-toggle {
  display: none;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  color: var(--links-color);
  font-size: 22px;
  line-height: 1;
  transition: color 0.2s ease;
}

.menu-toggle:hover {
  color: var(--text-color);
}

/* 移动端右侧登录/注册（桌面端隐藏） */
.login-mobile {
  display: none;
  color: var(--links-color);
  text-decoration: none;
  font-size: 16px;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.login-mobile:hover {
  color: var(--text-color);
}

/* 移动端折叠菜单 */
.mobile-menu {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 1001;

  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;

  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.mobile-menu a {
  padding: 12px 16px;
  border-radius: 10px;
  color: var(--links-color);
  text-decoration: none;
  font-size: 16px;
  transition: all 0.15s ease;
}

.mobile-menu a:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

/* 折叠菜单展开/收起过渡 */
.slide-enter-active,
.slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* 移动端：三段式布局（左折叠 / 中 LOGO / 右登录注册） */
@media (max-width: 768px) {
  .navbar {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    padding: 0 16px;
  }

  .menu-toggle {
    display: flex;
    justify-self: start;
  }

  .logo {
    justify-self: center;
  }

  /* 移动端 LOGO 不带文字 */
  .logo-text {
    display: none;
  }

  .nav-right {
    display: none;
  }

  .user-fab {
    display: none;
  }

  .login-mobile {
    display: inline-flex;
    justify-self: end;
  }

  /* 移动端消息图标始终固定在左下角，不吸附 */
  .message-fab.attached {
    top: calc(100vh - 72px);
    left: 24px;
  }

  /* 移动端返回按钮不随滚动左移（消息按钮不吸附到顶部） */
  .back-fab.scrolled {
    left: calc(50% - min(540px, 45%) - 60px);
  }
}
</style>

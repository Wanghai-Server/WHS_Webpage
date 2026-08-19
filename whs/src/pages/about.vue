<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { animate, stagger } from 'animejs'
import {
  Zap, TrainFront, Boxes, Users,
  Landmark, Vote, BookOpen, Scale,
  Mountain, Map, Sparkles, Hammer,
  Ban, Globe, Activity, Bot,
  Copy, Check, ArrowDown, ChevronRight,
} from 'lucide-vue-next'

import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import { copyText } from '../composables/clipboard'

const { t, tm } = useI18n()
const router = useRouter()

// ---------------------------------------------------------------------------
// 内容数据：全部来自 locales（pages.about.*），页面内零硬编码文案
// ---------------------------------------------------------------------------
const visionItems = tm('pages.about.vision.items')
const historyItems = tm('pages.about.history.items')
const governanceItems = tm('pages.about.governance.items')
const featureItems = tm('pages.about.features.items')
const ruleItems = tm('pages.about.rules.items')
const teamMembers = tm('pages.about.team.members')
const joinSteps = tm('pages.about.join.steps')
const stats = tm('pages.about.stats')

// 各区块卡片图标（与词条数组按下标一一对应）
const visionIcons = [Zap, TrainFront, Boxes, Users]
const governanceIcons = [Landmark, Vote, BookOpen, Scale]
const featureIcons = [Boxes, TrainFront, Mountain, Map, Sparkles, Hammer]
const ruleIcons = [Ban, Globe, Activity]

// 团队成员角色
const roleKeys = { owner: 'role_owner', co_owner: 'role_co_owner', admin: 'role_admin' }
function roleLabel(role) {
  return t(`pages.about.team.${roleKeys[role] || 'role_admin'}`)
}

// 头像：优先 mc-heads 按玩家名取 Minecraft 皮肤头像，加载失败回退首字母徽章
const avatarFailed = ref([])
function mcAvatarUrl(name) {
  return `https://mc-heads.net/avatar/${encodeURIComponent(String(name))}/64`
}
function onAvatarError(index) {
  avatarFailed.value[index] = true
}
function initialOf(name) {
  return String(name || '?').charAt(0).toUpperCase()
}
// 回退徽章渐变底色
const avatarGradients = [
  'linear-gradient(135deg, #ebaa28, #e07b1f)',
  'linear-gradient(135deg, #38bdf8, #2563eb)',
  'linear-gradient(135deg, #34d399, #059669)',
  'linear-gradient(135deg, #f472b6, #db2777)',
  'linear-gradient(135deg, #a78bfa, #7c3aed)',
  'linear-gradient(135deg, #fbbf24, #f59e0b)',
  'linear-gradient(135deg, #22d3ee, #0ea5e9)',
]
function avatarBg(index) {
  return avatarGradients[index % avatarGradients.length]
}

// ---------------------------------------------------------------------------
// 服务器实时状态：GET /api/server/status（后端每 5 分钟探测并缓存）
// ---------------------------------------------------------------------------
const serverStatus = ref(null)
const statusOnline = computed(() => serverStatus.value?.online === true)

const tpsClass = computed(() => {
  const tps = serverStatus.value?.tps
  if (tps == null) return ''
  if (tps >= 18) return 'tps-good'
  if (tps >= 15) return 'tps-mid'
  return 'tps-bad'
})

async function fetchServerStatus() {
  try {
    const res = await fetch('/api/server/status')
    const data = await res.json().catch(() => null)
    if (res.ok && data) {
      serverStatus.value = data
      return
    }
  } catch (e) {
    console.warn(e)
  }
  // 后端不可达时按离线处理（下一轮 5 分钟轮询会重试）
  serverStatus.value = {
    online: false,
    version: '',
    players: { online: 0, max: 0 },
    latency_ms: null,
    tps: null,
  }
}

let statusTimer = null

// 复制世界种子
const copied = ref(false)
let copyTimer = null
async function copySeed() {
  const ok = await copyText('wanghai_commune')
  if (ok) {
    copied.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copied.value = false), 2000)
  }
}

// ---------------------------------------------------------------------------
// 英雄区：懒加载随机截图（与首页同款）+ 入场动画
// ---------------------------------------------------------------------------
const pageRef = ref(null)
const heroRef = ref(null)
const bgImage = ref('')
const bgLoaded = ref(false)
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

let observer = null

onMounted(() => {
  // 1) 英雄背景：从服务器截图中随机一张，加载完成后淡入（避免首屏解析全部大图）
  const modules = import.meta.glob(['../assets/background.png', '../assets/wanghai_web/*.png'])
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

  // 2) 英雄区入场动画（尊重"减少动态效果"偏好；CSS 中也兜底了 .hero-fade 的可见性）
  if (!reducedMotion && heroRef.value) {
    animate(heroRef.value.querySelectorAll('.hero-fade'), {
      opacity: [0, 1],
      translateY: [28, 0],
      duration: 900,
      delay: stagger(140),
      ease: 'outQuad',
    })
  }

  // 3) 服务器状态：立即拉取一次，之后每 5 分钟轮询（与后端缓存节奏一致）
  fetchServerStatus()
  statusTimer = setInterval(fetchServerStatus, 300000)

  // 4) 滚动显现：进入视口后上浮淡入
  const els = pageRef.value?.querySelectorAll('.reveal') || []
  if (reducedMotion) {
    els.forEach((el) => el.classList.add('visible'))
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible')
          observer.unobserve(entry.target)
        }
      }
    },
    { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
  )
  els.forEach((el) => observer.observe(el))
})

onUnmounted(() => {
  if (observer) observer.disconnect()
  clearInterval(statusTimer)
  clearTimeout(copyTimer)
})
</script>

<template>
  <Top_navbar />

  <main ref="pageRef" class="about-page">
    <!-- ==================== 1. 英雄区 ==================== -->
    <section ref="heroRef" class="hero">
      <div
        class="hero-bg"
        :class="{ loaded: bgLoaded }"
        :style="bgImage ? { backgroundImage: `url(${bgImage})` } : {}"
      ></div>
      <div class="hero-overlay">
        <h1 class="hero-fade">{{ t('pages.about.hero.title') }}</h1>
        <p class="hero-sub hero-fade">{{ t('pages.about.hero.subtitle') }}</p>
        <div class="scroll-hint">
          <div class="scroll-hint-inner hero-fade">
            <span>{{ t('pages.about.hero.scroll') }}</span>
            <ArrowDown :size="18" class="scroll-arrow" />
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 2. 社区愿景 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.vision.title') }}</h2>
      </div>

      <p class="vision-text reveal">{{ t('pages.about.vision.text') }}</p>

      <div class="card-grid cols-4">
        <div
          v-for="(item, i) in visionItems"
          :key="i"
          class="reveal"
          :style="{ transitionDelay: `${i * 70}ms` }"
        >
          <div class="glass-card">
            <div class="card-icon">
              <component :is="visionIcons[i]" :size="22" />
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 3. 服务器状态 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.stats.title') }}</h2>
      </div>

      <div class="stats-panel reveal">
        <!-- 在线状态 -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.status.label }}</span>
          <span class="stat-value status-value" :class="statusOnline ? 'is-online' : 'is-offline'">
            <span class="status-dot"></span>
            <template v-if="serverStatus">
              {{ statusOnline ? t('pages.about.stats.status.online') : t('pages.about.stats.status.offline') }}
            </template>
            <template v-else>{{ t('pages.about.stats.loading') }}</template>
          </span>
        </div>
        <!-- 在线人数 -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.players.label }}</span>
          <span class="stat-value stat-value-sm">
            <template v-if="serverStatus">
              {{ serverStatus.players.online }} / {{ serverStatus.players.max }}
            </template>
            <template v-else>{{ t('pages.about.stats.loading') }}</template>
          </span>
        </div>
        <!-- TPS -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.tps.label }}</span>
          <span class="stat-value" :class="tpsClass">
            <template v-if="serverStatus">
              {{ serverStatus.tps ?? t('pages.about.stats.tps.unavailable') }}
            </template>
            <template v-else>{{ t('pages.about.stats.loading') }}</template>
          </span>
          <span v-if="serverStatus && serverStatus.tps == null" class="stat-note">
            {{ t('pages.about.stats.tps.pending') }}
          </span>
        </div>
        <!-- 游戏版本 -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.version.label }}</span>
          <span class="stat-value stat-value-sm">{{ serverStatus?.version || stats.version.value }}</span>
          <span class="stat-note">{{ stats.version.note }}</span>
        </div>
        <!-- 当前周目 -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.round.label }}</span>
          <span class="stat-value">{{ stats.round.value }}</span>
        </div>
        <!-- 服务器性质 -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.nature.label }}</span>
          <span class="stat-value stat-value-sm">{{ stats.nature.value }}</span>
        </div>
        <!-- 世界种子（整行，点击复制） -->
        <div
          class="stat-cell seed-cell"
          role="button"
          tabindex="0"
          :aria-label="stats.seed.note"
          @click="copySeed"
          @keydown.enter="copySeed"
        >
          <span class="stat-label">{{ stats.seed.label }}</span>
          <span class="stat-value seed-value">
            {{ stats.seed.value }}
            <span class="seed-copy">
              <Check v-if="copied" :size="14" />
              <Copy v-else :size="14" />
            </span>
          </span>
          <span class="stat-note">
            {{ copied ? t('pages.about.copied') : stats.seed.note }}
          </span>
        </div>
      </div>
    </section>

    <!-- ==================== 4. 历史沿革 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.history.title') }}</h2>
      </div>

      <div class="timeline">
        <div
          v-for="(item, i) in historyItems"
          :key="i"
          class="tl-item reveal"
          :style="{ transitionDelay: `${i * 80}ms` }"
        >
          <span class="tl-dot"></span>
          <div class="tl-card glass-card">
            <span class="tl-time">{{ item.time }}</span>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 5. 社区与治理 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.governance.title') }}</h2>
      </div>

      <div class="card-grid cols-4">
        <div
          v-for="(item, i) in governanceItems"
          :key="i"
          class="reveal"
          :style="{ transitionDelay: `${i * 70}ms` }"
        >
          <div class="glass-card">
            <div class="card-icon">
              <component :is="governanceIcons[i]" :size="22" />
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 6. 特色玩法 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.features.title') }}</h2>
      </div>

      <div class="card-grid cols-3">
        <div
          v-for="(item, i) in featureItems"
          :key="i"
          class="reveal"
          :style="{ transitionDelay: `${(i % 3) * 70}ms` }"
        >
          <div class="glass-card">
            <div class="card-icon">
              <component :is="featureIcons[i]" :size="22" />
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>

      <!-- GamesAI 特别说明：服务器已接入 AI -->
      <div class="ai-callout reveal">
        <div class="card-icon">
          <Bot :size="24" />
        </div>
        <div class="ai-callout-body">
          <h3>{{ t('pages.about.features.aiTitle') }}</h3>
          <p>{{ t('pages.about.features.aiText') }}</p>
          <a
            class="ai-link"
            href="https://github.com/PengZixuan30/Games_AI"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ t('pages.about.features.aiLink') }}
            <ChevronRight :size="16" />
          </a>
        </div>
      </div>
    </section>

    <!-- ==================== 7. 行为规范 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.rules.title') }}</h2>
      </div>

      <div class="card-grid cols-3">
        <div
          v-for="(item, i) in ruleItems"
          :key="i"
          class="reveal"
          :style="{ transitionDelay: `${i * 70}ms` }"
        >
          <div class="glass-card">
            <div class="card-icon">
              <component :is="ruleIcons[i]" :size="22" />
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>

      <div class="rules-action reveal">
        <button type="button" class="gold-btn" @click="router.push('/joinus')">
          {{ t('pages.about.rules.fullRules') }}
          <ChevronRight :size="18" />
        </button>
        <p class="rules-hint">{{ t('pages.about.rules.fullRulesHint') }}</p>
      </div>
    </section>

    <!-- ==================== 8. 团队成员 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.team.title') }}</h2>
      </div>

      <div class="team-grid">
        <div
          v-for="(m, i) in teamMembers"
          :key="i"
          class="reveal"
          :style="{ transitionDelay: `${(i % 4) * 60}ms` }"
        >
          <div class="team-card glass-card">
            <div class="team-avatar" :style="{ background: avatarBg(i) }">
              <img
                v-if="!avatarFailed[i]"
                :src="mcAvatarUrl(m.name)"
                :alt="m.name"
                loading="lazy"
                @error="onAvatarError(i)"
              />
              <span v-else>{{ initialOf(m.name) }}</span>
            </div>
            <div class="team-info">
              <h3>{{ m.name }}</h3>
              <span class="team-role" :class="{ gold: m.role !== 'admin' }">{{ roleLabel(m.role) }}</span>
              <p>{{ m.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 9. 加入我们 ==================== -->
    <section class="section join-section">
      <div class="join-panel reveal">
        <div class="section-head">
          <span class="head-bar"></span>
          <h2>{{ t('pages.about.join.title') }}</h2>
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
          {{ t('pages.about.join.button') }}
          <ChevronRight :size="20" />
        </button>
        <p class="join-hint">{{ t('pages.about.join.hint') }}</p>
      </div>
    </section>
  </main>

  <Page_footer />
</template>

<style scoped>
/* ------------------------------------------------------------------ */
/* 英雄区（grid 覆盖布局：背景与内容严格同格，内容天然水平/垂直居中）  */
/* ------------------------------------------------------------------ */
.hero {
  position: relative;
  width: 100%;
  min-height: 100vh;
  display: grid;
  overflow: hidden;
  background-color: var(--bg-color); /* 图片加载完成前的占位底色 */
}

.hero-bg {
  grid-area: 1 / 1;
  width: 100%;
  height: 100%;
  background-size: cover;
  background-repeat: no-repeat;
  background-position: center;
  opacity: 0;
  transition: opacity 0.8s ease;
}

.hero-bg.loaded {
  opacity: 1;
}

.hero-overlay {
  grid-area: 1 / 1;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 100px 24px 110px;
  box-sizing: border-box;
  background: linear-gradient(180deg, rgba(11, 29, 58, 0.45) 0%, rgba(0, 0, 0, 0.6) 100%);
}

/* 入场动画目标元素：默认隐藏，由 animejs 淡入；减少动效时直接显示 */
.hero-fade {
  opacity: 0;
}

.hero h1 {
  margin: 0 0 18px;
  font-size: 56px;
  font-weight: 800;
  color: #ffffff;
}

.hero-sub {
  margin: 0;
  max-width: 720px;
  font-size: 20px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.9);
}

/* 滚动提示：外层只负责定位与水平居中（不依赖 transform，
   避免入场动画覆盖 transform 导致偏移）；动画只作用于内层 */
.scroll-hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 30px;
  display: flex;
  justify-content: center;
  pointer-events: none;
}

.scroll-hint-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  letter-spacing: 0.2em;
  white-space: nowrap;
}

.scroll-arrow {
  animation: scroll-bounce 1.8s ease-in-out infinite;
}

@keyframes scroll-bounce {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.6;
  }
  50% {
    transform: translateY(8px);
    opacity: 1;
  }
}

/* ------------------------------------------------------------------ */
/* 通用区块                                                            */
/* ------------------------------------------------------------------ */
.section {
  max-width: 1100px;
  margin: 0 auto;
  padding: 96px 24px;
  box-sizing: border-box;
}

.section-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin-bottom: 44px;
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

.vision-text {
  margin: 0 auto 44px;
  max-width: 780px;
  font-size: 17px;
  line-height: 1.9;
  text-align: center;
  color: var(--text-color);
}

/* ------------------------------------------------------------------ */
/* 玻璃卡片（.reveal 在卡片外层包装上，hover 位移与显现动画互不冲突） */
/* ------------------------------------------------------------------ */
.glass-card {
  height: 100%;
  box-sizing: border-box;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  padding: 28px 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease,
    border-color 0.25s ease;
}

.glass-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 20px 44px rgba(0, 0, 0, 0.14);
  border-color: rgba(235, 170, 40, 0.5);
}

.card-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(235, 170, 40, 0.14);
  color: #ebaa28;
  margin-bottom: 16px;
}

.glass-card h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.glass-card p {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.7;
  color: var(--links-color);
}

.card-grid {
  display: grid;
  gap: 20px;
}

.cols-4 {
  grid-template-columns: repeat(4, 1fr);
}

.cols-3 {
  grid-template-columns: repeat(3, 1fr);
}

/* ------------------------------------------------------------------ */
/* 服务器状态（数据格）                                                */
/* ------------------------------------------------------------------ */
.stats-panel {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: rgba(148, 163, 184, 0.18);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  overflow: hidden;
}

.stat-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--card-color);
  padding: 30px 20px;
  text-align: center;
  transition: background-color 0.2s ease;
}

.stat-label {
  font-size: 13px;
  color: var(--links-color);
}

.stat-value {
  font-size: 34px;
  font-weight: 800;
  line-height: 1.2;
  color: var(--text-color);
  font-variant-numeric: tabular-nums;
}

.stat-value-sm {
  font-size: 26px;
}

.stat-note {
  font-size: 12px;
  color: var(--links-color);
}

/* 在线状态：绿点 / 红点 */
.status-value {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 30px;
}

.status-value.is-online {
  color: #22c55e;
}

.status-value.is-offline {
  color: #ef4444;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 10px currentColor;
}

/* TPS 分级着色 */
.tps-good {
  color: #22c55e;
}

.tps-mid {
  color: #eab308;
}

.tps-bad {
  color: #ef4444;
}

/* 种子单元格：整行 + 可点击复制 */
.seed-cell {
  grid-column: 1 / -1;
  flex-direction: row;
  flex-wrap: wrap;
  column-gap: 14px;
  row-gap: 4px;
  padding: 22px 20px;
  cursor: pointer;
}

.seed-cell:hover {
  background: rgba(235, 170, 40, 0.06);
}

.seed-value {
  font-size: 24px;
  letter-spacing: 0.5px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.seed-copy {
  display: inline-flex;
  color: #ebaa28;
}

/* ------------------------------------------------------------------ */
/* 历史时间线                                                          */
/* ------------------------------------------------------------------ */
.timeline {
  position: relative;
  padding: 8px 0;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  transform: translateX(-50%);
  background: linear-gradient(180deg, rgba(235, 170, 40, 0.08), rgba(235, 170, 40, 0.6), rgba(235, 170, 40, 0.08));
}

.tl-item {
  position: relative;
  width: 50%;
  padding: 0 44px 48px 0;
  box-sizing: border-box;
}

.tl-item:nth-child(even) {
  margin-left: 50%;
  padding: 0 0 48px 44px;
}

.tl-item:last-child {
  padding-bottom: 8px;
}

.tl-dot {
  position: absolute;
  top: 10px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #ebaa28;
  border: 3px solid var(--bg-color);
  box-shadow: 0 0 0 3px rgba(235, 170, 40, 0.3);
}

.tl-item:nth-child(odd) .tl-dot {
  right: -7px;
}

.tl-item:nth-child(even) .tl-dot {
  left: -7px;
}

.tl-card {
  padding: 24px;
}

.tl-time {
  display: block;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.2em;
  color: #ebaa28;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.tl-card h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.tl-card p {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.7;
  color: var(--links-color);
}

/* ------------------------------------------------------------------ */
/* GamesAI 特别说明                                                    */
/* ------------------------------------------------------------------ */
.ai-callout {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  margin-top: 20px;
  padding: 28px 28px;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(235, 170, 40, 0.1), rgba(235, 170, 40, 0.03));
  border: 1px solid rgba(235, 170, 40, 0.3);
}

.ai-callout .card-icon {
  flex-shrink: 0;
  margin-bottom: 0;
}

.ai-callout-body h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.ai-callout-body p {
  margin: 0 0 12px;
  font-size: 14.5px;
  line-height: 1.7;
  color: var(--links-color);
}

.ai-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #ebaa28;
  text-decoration: none;
  transition: color 0.2s ease;
}

.ai-link:hover {
  color: #d99a1f;
}

/* ------------------------------------------------------------------ */
/* 规则                                                               */
/* ------------------------------------------------------------------ */
.rules-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-top: 44px;
}

.rules-hint {
  margin: 0;
  font-size: 13px;
  color: var(--links-color);
}

/* ------------------------------------------------------------------ */
/* 团队成员                                                            */
/* ------------------------------------------------------------------ */
.team-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(215px, 1fr));
  gap: 20px;
}

.team-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
}

.team-avatar {
  position: relative;
  width: 54px;
  height: 54px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-size: 24px;
  font-weight: 800;
  flex-shrink: 0;
  overflow: hidden;
}

.team-avatar img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.team-info h3 {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-color);
  word-break: break-all;
}

.team-role {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
  color: var(--links-color);
  margin-bottom: 6px;
}

.team-role.gold {
  background: rgba(235, 170, 40, 0.16);
  color: #ebaa28;
}

.team-info p {
  margin: 0;
  font-size: 12.5px;
  color: var(--links-color);
}

/* ------------------------------------------------------------------ */
/* 加入我们                                                            */
/* ------------------------------------------------------------------ */
.join-section {
  padding-bottom: 120px;
}

.join-panel {
  text-align: center;
  background: linear-gradient(135deg, rgba(235, 170, 40, 0.09), rgba(235, 170, 40, 0.02));
  border: 1px solid rgba(235, 170, 40, 0.28);
  border-radius: 24px;
  padding: 48px 32px 44px;
}

.join-panel .section-head {
  margin-bottom: 40px;
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

/* ------------------------------------------------------------------ */
/* 滚动显现（作用于包装元素，与卡片 hover 位移互不冲突）               */
/* ------------------------------------------------------------------ */
.reveal {
  opacity: 0;
  transform: translateY(26px);
  transition:
    opacity 0.6s ease,
    transform 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}

.reveal.visible {
  opacity: 1;
  transform: none;
}

/* ------------------------------------------------------------------ */
/* 减少动态效果                                                        */
/* ------------------------------------------------------------------ */
@media (prefers-reduced-motion: reduce) {
  .hero-fade {
    opacity: 1;
  }

  .scroll-arrow {
    animation: none;
  }

  .reveal {
    opacity: 1;
    transform: none;
    transition: none;
  }
}

/* ------------------------------------------------------------------ */
/* 响应式                                                              */
/* ------------------------------------------------------------------ */
@media (max-width: 900px) {
  .cols-4 {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .section {
    padding: 72px 20px;
  }

  .section-head h2 {
    font-size: 26px;
  }

  .hero h1 {
    font-size: 36px;
  }

  .hero-sub {
    font-size: 16px;
  }

  .cols-3 {
    grid-template-columns: 1fr;
  }

  .stats-panel {
    grid-template-columns: repeat(2, 1fr);
  }

  /* 时间线改为左侧对齐 */
  .timeline::before {
    left: 12px;
    transform: none;
  }

  .tl-item,
  .tl-item:nth-child(even) {
    width: 100%;
    margin-left: 0;
    padding: 0 0 36px 44px;
  }

  .tl-dot,
  .tl-item:nth-child(odd) .tl-dot,
  .tl-item:nth-child(even) .tl-dot {
    left: 5px;
    right: auto;
  }

  .ai-callout {
    flex-direction: column;
    gap: 14px;
  }

  .join-steps {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .cols-4 {
    grid-template-columns: 1fr;
  }

  .stats-panel {
    grid-template-columns: 1fr;
  }

  .join-steps {
    grid-template-columns: 1fr;
  }
}
</style>

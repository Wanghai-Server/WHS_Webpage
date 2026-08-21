<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { animate, stagger } from 'animejs'
import {
  Zap, TrainFront, Boxes, Users,
  Landmark, Vote, BookOpen, Scale,
  Mountain, Map, Sparkles, Hammer,
  Ban, Globe, Activity, Bot, User,
  Copy, Check, ArrowDown, ChevronRight, ExternalLink,
  ShieldCheck, GraduationCap, Bell, Cpu,
} from 'lucide-vue-next'

import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import JoinusTips from '../components/joinus_tips.vue'
import PlayerInfo from '../components/player_info.vue'
import { copyText } from '../composables/clipboard'

const { t, tm } = useI18n()
const router = useRouter()

// ---------------------------------------------------------------------------
// 内容数据：全部来自 locales（pages.about.* / join.*），页面内零硬编码文案
// ---------------------------------------------------------------------------
// tm() 本身读取 vue-i18n 的响应式依赖但不具响应性：必须在 computed 中调用，
// 语言切换时才会重新求值、跟随翻译（模板中自动解包，无需 .value）
const visionItems = computed(() => tm('pages.about.vision.items'))
const historyItems = computed(() => tm('pages.about.history.items'))
const governanceItems = computed(() => tm('pages.about.governance.items'))
const featureItems = computed(() => tm('pages.about.features.items'))
const ruleItems = computed(() => tm('pages.about.rules.items'))
const teamMembers = computed(() => tm('pages.about.team.members'))
const stats = computed(() => tm('pages.about.stats'))
const aboutItems = computed(() => tm('pages.about.about.items'))

// 各区块卡片图标（与词条数组按下标一一对应）
const visionIcons = [Zap, TrainFront, Boxes, Users]
const governanceIcons = [Landmark, Vote, BookOpen, Scale]
const featureIcons = [Boxes, TrainFront, Mountain, Map, Sparkles, Hammer]
const ruleIcons = [Ban, Globe, Activity]
const aboutIcons = [ShieldCheck, GraduationCap, Activity, Bell, Users, Globe]

// 团队成员角色
const roleKeys = { owner: 'role_owner', co_owner: 'role_co_owner', admin: 'role_admin' }
function roleLabel(role) {
  return t(`pages.about.team.${roleKeys[role] || 'role_admin'}`)
}

// 团队成员：卡片展示 mc-heads 全身模型图，点击打开 player_info 悬浮窗
const modelFailed = ref([])
function mcBodyUrl(playerName) {
  return `https://mc-heads.net/body/${encodeURIComponent(String(playerName))}/front/256`
}
function onModelError(index) {
  modelFailed.value[index] = true
}

// 当前打开的成员（player_info 悬浮窗数据源）
const activePlayer = ref(null)
function openPlayer(member) {
  activePlayer.value = member
}

// ---------------------------------------------------------------------------
// 服务器实时状态：GET /api/server/status（数据全部来自 MCDR 插件：
// 在线名单/TPS/MSPT/玩家上限；后端每 5 分钟刷新缓存，前端同步轮询）
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
    players: { online: 0, max: 0 },
    tps: null,
  }
}

let statusTimer = null

// ---------------------------------------------------------------------------
// 成员墙：获取白名单玩家（/api/server/whitelist），用 mc-heads 头像服务
// 只展示头像；点击头像打开可复用的 player_info 悬浮窗（3D 模型 + 主页跳转）
// ---------------------------------------------------------------------------
const members = ref([])
const membersLoading = ref(false)
const membersFailed = ref(false)
// 头像加载失败的玩家名（mc-heads 对离线/未知玩家可能返回 404）→ 显示占位图标
const avatarFailedNames = ref(new Set())

function memberAvatar(name) {
  return `https://mc-heads.net/avatar/${encodeURIComponent(String(name))}/96`
}

function avatarFailed(name) {
  return avatarFailedNames.value.has(name)
}

function onAvatarError(name) {
  avatarFailedNames.value.add(name)
}

async function fetchMembers() {
  membersLoading.value = true
  membersFailed.value = false
  try {
    const res = await fetch('/api/server/whitelist')
    const data = await res.json().catch(() => null)
    if (res.ok && data && Array.isArray(data.players)) {
      members.value = data.players
    } else {
      membersFailed.value = true
    }
  } catch (e) {
    console.warn(e)
    membersFailed.value = true
  } finally {
    membersLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 世界种子：点击复制种子；旁边提供 ChunkBase 完整地图外链
// （种子图弹窗已回退，后续考虑经 MCDR 插件解析 .mca 实现种子图）
// ---------------------------------------------------------------------------
const chunkbaseMapUrl = `https://www.chunkbase.com/apps/seed-map#seed=${encodeURIComponent(stats.value.seed.mapSeed)}`

// 复制世界种子
const copied = ref(false)
let copyTimer = null
async function copySeed() {
  const ok = await copyText(stats.value.seed.value)
  if (ok) {
    copied.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copied.value = false), 2000)
  }
}

// ---------------------------------------------------------------------------
// 历史沿革：横向推进章节（sticky 锁定式）
// 章节嵌入页面总高度（100vh + 横向行程）：页面正常滚动，当章节滚动到
// 视口时 sticky 容器锁定不动，卡片按页面滚动进度横向平移，主轴保持固定。
// 滚轮在页面任意位置滚动都会驱动它，不会"跳过"。
// ---------------------------------------------------------------------------
const timelineSectionRef = ref(null)
const timelineTrackRef = ref(null)

// 卡片轨道需要横向平移的总距离（轨道宽 - 可视宽）
let timelineShift = 0

function updateTimelineLayout() {
  const section = timelineSectionRef.value
  const track = timelineTrackRef.value
  if (!section || !track) return
  timelineShift = Math.max(0, track.scrollWidth - track.clientWidth)
  // 章节高度 = 一屏 + 横向行程：滚动完这段额外距离，卡片恰好从头走到尾
  section.style.height = `calc(100vh + ${timelineShift}px)`
  applyTimelineProgress()
}

function applyTimelineProgress() {
  const section = timelineSectionRef.value
  const track = timelineTrackRef.value
  if (!section || !track || timelineShift <= 0) return
  const total = section.offsetHeight - window.innerHeight
  if (total <= 0) return
  const top = section.getBoundingClientRect().top
  // 章节远离视口时跳过，避免无意义的样式写入
  if (top > window.innerHeight || top < -total - window.innerHeight) return
  const progress = Math.min(1, Math.max(0, -top / total))
  track.style.transform = `translate3d(${(-progress * timelineShift).toFixed(1)}px, 0, 0)`
}

function onPageScroll() {
  applyTimelineProgress()
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

  // 4) 成员墙：拉取白名单玩家列表（头像由 mc-heads 提供）
  fetchMembers()

  // 5) 时间线：计算章节高度，随页面滚动横向推进（页面任意位置滚动均生效）
  updateTimelineLayout()
  window.addEventListener('scroll', onPageScroll, { passive: true })
  window.addEventListener('resize', updateTimelineLayout)

  // 6) 滚动显现：进入视口后上浮淡入
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
  window.removeEventListener('scroll', onPageScroll)
  window.removeEventListener('resize', updateTimelineLayout)
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
        <!-- 游戏版本（硬编码，不再依赖后端探测） -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.version.label }}</span>
          <span class="stat-value stat-value-sm">{{ stats.version.value }}</span>
          <span class="stat-note">{{ stats.version.note }}</span>
        </div>
        <!-- 当前周目 -->
        <div class="stat-cell">
          <span class="stat-label">{{ stats.round.label }}</span>
          <span class="stat-value">{{ stats.round.value }}</span>
        </div>
        <!-- 世界种子（普通格尺寸，点击复制，右上角外链打开 ChunkBase 完整地图） -->
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
          <a
            class="seed-chunkbase-link"
            :href="chunkbaseMapUrl"
            target="_blank"
            rel="noopener noreferrer"
            :aria-label="stats.seed.open"
            :title="stats.seed.open"
            @click.stop
          >
            <ExternalLink :size="16" />
          </a>
        </div>
      </div>
    </section>

    <!-- ==================== 4. 历史沿革（随页面滚动横向推进） ==================== -->
    <section ref="timelineSectionRef" class="section timeline-section">
      <div class="sticky-wrap">
        <div class="section-head reveal">
          <span class="head-bar"></span>
          <h2>{{ t('pages.about.history.title') }}</h2>
        </div>

        <div class="timeline">
          <!-- 主轴固定，不随卡片横向移动 -->
          <div class="timeline-line"></div>
          <div ref="timelineTrackRef" class="timeline-track">
            <div
              v-for="(item, i) in historyItems"
              :key="i"
              class="tl-item"
            >
              <div class="tl-date">{{ item.date }}</div>
              <span class="tl-dot"></span>
              <span class="tl-stem"></span>
              <div class="tl-card glass-card">
                <span class="tl-time">{{ item.time }}</span>
                <h3>{{ item.title }}</h3>
                <p>{{ item.desc }}</p>
              </div>
            </div>
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

      <div class="team-list">
        <div
          v-for="(m, i) in teamMembers"
          :key="i"
          class="team-row reveal"
          :class="{ reversed: i % 2 === 1 }"
          :style="{ transitionDelay: `${(i % 4) * 60}ms` }"
          role="button"
          tabindex="0"
          :aria-label="m.name"
          @click="openPlayer(m)"
          @keydown.enter="openPlayer(m)"
        >
          <div class="team-model">
            <img
              v-if="!modelFailed[i]"
              :src="mcBodyUrl(m.playerName)"
              :alt="m.name"
              loading="lazy"
              @error="onModelError(i)"
            />
            <span v-else class="team-model-fallback"><User :size="44" /></span>
          </div>
          <div class="team-info">
            <h3>{{ m.name }}</h3>
            <span class="team-role" :class="{ gold: m.role !== 'admin' }">{{ roleLabel(m.role) }}</span>
            <p>{{ m.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 9. 加入我们（可复用组件） ==================== -->
    <div class="reveal">
      <JoinusTips />
    </div>

    <!-- ==================== 10. 成员墙（白名单玩家头像，点击打开 player_info） ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.members.title') }}</h2>
      </div>

      <p class="vision-text reveal">{{ t('pages.about.members.text') }}</p>

      <!-- 整块"墙"卡片背景（高于网页背景）；内容为异步渲染故不带 reveal -->
      <div class="members-wall reveal">
        <div v-if="membersLoading" class="members-status">{{ t('pages.about.stats.loading') }}</div>
        <p v-else-if="membersFailed" class="members-status">{{ t('pages.about.members.loadFailed') }}</p>
        <p v-else-if="members.length === 0" class="members-status">{{ t('pages.about.members.empty') }}</p>
        <div v-else class="members-grid">
          <div
            v-for="name in members"
            :key="name"
            class="member-cell"
          >
            <!-- 悬浮名字标签：悬停成员格时在头像上方淡入显示 -->
            <span class="member-name">{{ name }}</span>
            <button
              type="button"
              class="member-avatar"
              :title="name"
              :aria-label="name"
              @click="openPlayer({ playerName: name, name })"
            >
              <img
                v-if="!avatarFailed(name)"
                :src="memberAvatar(name)"
                :alt="name"
                loading="lazy"
                @error="onAvatarError(name)"
              />
              <span v-else class="member-avatar-fallback"><User :size="16" /></span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 11. 关于此网站 ==================== -->
    <section class="section">
      <div class="section-head reveal">
        <span class="head-bar"></span>
        <h2>{{ t('pages.about.about.title') }}</h2>
      </div>

      <p class="vision-text reveal">{{ t('pages.about.about.text') }}</p>

      <div class="card-grid cols-3">
        <div
          v-for="(item, i) in aboutItems"
          :key="i"
          class="reveal"
          :style="{ transitionDelay: `${(i % 3) * 70}ms` }"
        >
          <div class="glass-card">
            <div class="card-icon">
              <component :is="aboutIcons[i]" :size="22" />
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>

      <!-- 技术栈说明（与 GamesAI 说明条同款样式） -->
      <div class="ai-callout reveal">
        <div class="card-icon">
          <Cpu :size="24" />
        </div>
        <div class="ai-callout-body">
          <h3>{{ t('pages.about.about.techTitle') }}</h3>
          <p>{{ t('pages.about.about.techText') }}</p>
        </div>
      </div>
    </section>
  </main>

  <!-- 玩家信息悬浮窗（可复用组件：3D 模型 + 主页跳转） -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <PlayerInfo
        v-if="activePlayer"
        :player-name="activePlayer.playerName"
        :display-name="activePlayer.name"
        @close="activePlayer = null"
      />
    </Transition>
  </Teleport>

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

/* 种子单元格：普通格尺寸（位于原"服务器性质"位置），整格可点击复制；
   右上角为 ChunkBase 完整地图外链按钮（不再单独占一整行） */
.seed-cell {
  position: relative;
  flex-direction: column;
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
  justify-content: center;
  gap: 8px;
  word-break: break-all;
  max-width: 100%;
}

.seed-copy {
  display: inline-flex;
  color: #ebaa28;
}

/* ChunkBase 完整地图外链（种子格右上角图标按钮） */
.seed-chunkbase-link {
  position: absolute;
  top: 10px;
  right: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: transparent;
  color: var(--links-color);
  text-decoration: none;
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.seed-chunkbase-link:hover {
  color: #ebaa28;
  border-color: rgba(235, 170, 40, 0.5);
  background: rgba(235, 170, 40, 0.08);
}

/* ------------------------------------------------------------------ */
/* 成员墙（白名单玩家头像，mc-heads 头像服务）                          */
/* 整块卡片背景（与全站 .glass-card / .stats-panel 风格一致），          */
/* 体现"墙"高于网页背景                                                */
/* ------------------------------------------------------------------ */
.members-wall {
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  padding: 28px 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
}

.members-subtitle {
  margin: 0 0 24px;
  max-width: 640px;
  font-size: 15px;
  line-height: 1.7;
  text-align: center;
  color: var(--links-color);
}

.members-status {
  margin: 0;
  padding: 40px 0;
  text-align: center;
  color: var(--links-color);
}

.members-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(48px, 1fr));
  gap: 12px;
  justify-items: center;
}

/* 成员格：头像按钮 + 悬浮名字标签的定位容器（宽度与按钮一致） */
.member-cell {
  position: relative;
  display: flex;
  justify-content: center;
}

/* 悬浮名字标签：悬停（或键盘聚焦）成员格时在头像上方淡入显示 */
.member-name {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translate(-50%, 4px);
  padding: 3px 10px;
  border-radius: 6px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.25);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
  color: var(--text-color);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
  z-index: 20;
}

/* 标签指向头像的小箭头 */
.member-name::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--card-color);
}

.member-cell:hover .member-name,
.member-cell:focus-within .member-name {
  opacity: 1;
  transform: translate(-50%, 0);
}

/* 方形头像（用户要求不裁剪成圆形；尺寸较小） */
.member-avatar {
  position: relative;
  display: block;
  width: 48px;
  height: 48px;
  padding: 0;
  border: none;
  border-radius: 0;
  background: var(--float-bg);
  cursor: pointer;
  overflow: hidden;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
  box-shadow: 0 0 0 3px transparent;
}

.member-avatar:hover {
  transform: translateY(-4px);
  box-shadow: 0 0 0 3px rgba(235, 170, 40, 0.55);
}

.member-avatar img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.member-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--links-color);
}

/* ------------------------------------------------------------------ */
/* 历史沿革：横向推进章节（sticky 锁定式）                             */
/* 章节占据 (100vh + 横向行程) 的页面高度：页面正常滚动，滚动到本段时  */
/* sticky 容器锁定在视口中，卡片轨道随滚动进度横向平移，主轴保持固定   */
/* ------------------------------------------------------------------ */
.timeline-section {
  /* 覆盖 .section 的垂直内边距：章节高度由 JS 按横向行程动态计算 */
  padding: 0 24px;
}

.sticky-wrap {
  position: sticky;
  top: 0;
  height: 100vh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  padding: 70px 0 50px; /* 顶部避开固定导航栏，底部留白 */
}

.timeline {
  position: relative;
  width: 100%;
}

/* 横向金色轴线：定位在 .timeline（非平移元素）上，始终固定横贯可视区 */
.timeline-line {
  position: absolute;
  top: 58px;
  left: 0;
  right: 0;
  height: 2px;
  pointer-events: none;
  background: linear-gradient(
    90deg,
    rgba(235, 170, 40, 0.05),
    rgba(235, 170, 40, 0.55) 12%,
    rgba(235, 170, 40, 0.55) 88%,
    rgba(235, 170, 40, 0.05)
  );
}

/* 卡片轨道：随页面滚动进度横向平移（transform 由 JS 设置） */
.timeline-track {
  display: flex;
  gap: 48px; /* 卡片间距：拉开，避免相互之间太近 */
  padding: 0 8px;
  will-change: transform;
}

.tl-item {
  position: relative;
  flex: 0 0 320px;
  /* 顶部留白：时间点（日期/圆点/连接线）画在上方，卡片在轴线下方 */
  padding-top: 88px;
}

/* 事件时间：轴线上方的日期胶囊 */
.tl-date {
  position: absolute;
  top: 2px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid rgba(235, 170, 40, 0.4);
  background: var(--bg-color);
  color: #ebaa28;
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  z-index: 1;
}

/* 轴线上方的节点圆点 */
.tl-dot {
  position: absolute;
  top: 34px;
  left: 50%;
  transform: translateX(-50%);
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #ebaa28;
  border: 3px solid var(--bg-color);
  box-shadow: 0 0 0 3px rgba(235, 170, 40, 0.3);
  z-index: 1;
}

/* 圆点到轴线之间的连接线 */
.tl-stem {
  position: absolute;
  top: 48px;
  left: 50%;
  transform: translateX(-50%);
  width: 2px;
  height: 10px;
  background: rgba(235, 170, 40, 0.55);
  z-index: 1;
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

/* 金色胶囊按钮（与「加入我们」组件同款，组件 scoped 样式不跨组件生效） */
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

/* ------------------------------------------------------------------ */
/* 团队成员：整行交替布局（无背景卡片）                                */
/* ------------------------------------------------------------------ */
.team-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.team-row {
  display: flex;
  align-items: center;
  gap: 56px;
  padding: 32px 20px;
  border-radius: 20px;
  cursor: pointer;
  transition: background-color 0.25s ease;
}

/* 无背景：悬停时仅轻微底色提示可点击 */
.team-row:hover {
  background: rgba(235, 170, 40, 0.05);
}

/* 交替布局：奇数行模型在左/内容在右；偶数行模型在右/内容在左 */
.team-row.reversed {
  flex-direction: row-reverse;
}

.team-model {
  flex-shrink: 0;
}

.team-model img {
  display: block;
  height: 200px;
  width: auto;
}

.team-model-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 140px;
  height: 200px;
  color: var(--links-color);
}

.team-info {
  flex: 1;
  min-width: 0;
}

.team-info h3 {
  margin: 0 0 10px;
  font-size: 26px;
  font-weight: 800;
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
}

.team-role.gold {
  background: rgba(235, 170, 40, 0.16);
  color: #ebaa28;
}

.team-info p {
  margin: 10px 0 0;
  font-size: 15px;
  line-height: 1.8;
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

  /* 时间线卡片在移动端更宽，便于阅读 */
  .timeline-track {
    gap: 28px;
  }

  .tl-item {
    flex: 0 0 78vw;
  }

  .ai-callout {
    flex-direction: column;
    gap: 14px;
  }

  /* 团队行：移动端改为上下堆叠，模型在上、内容在下 */
  .team-row,
  .team-row.reversed {
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 14px;
    padding: 24px 12px;
  }

  .team-model img {
    height: 160px;
  }

  .team-model-fallback {
    height: 160px;
  }
}

@media (max-width: 480px) {
  .cols-4 {
    grid-template-columns: 1fr;
  }

  .stats-panel {
    grid-template-columns: 1fr;
  }
}
</style>

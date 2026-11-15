<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import { useAuth } from '../composables/useAuth'

const { t } = useI18n()
const { state: authState } = useAuth()

const wrapEl = ref(null)
const frameEl = ref(null)
const maps = ref([])
const activeMap = ref('')
const playerCount = ref(0)
// 2D / 3D 只是同一个 BlueMap 网页端的两种视图，记住上次选择
const viewMode = ref(localStorage.getItem('whs_map_view') === '3d' ? '3d' : '2d')
const viewer = ref('')
const startPos = ref([0, 0])
const startY = ref(80)
const available = ref(false)
const loaded = ref(false)
const failed = ref(false)
const immersive = ref(false)
const showControls = ref(false)
const gate = ref(null)
const loading = ref(true)
// 换图或换视图时递增，强制重建 iframe，让 BlueMap 按新参数初始化
const frameKey = ref(0)

let configTimer = null
let playersTimer = null
let loadTimer = null
let controlsTimer = null

// BlueMap 5.x 的 hash 共 10 段：
// mapId:x:y:z:distance:rotation:angle:tilt:ortho:view
// ortho 是数字（1=正交），view 必须是 flat / perspective 字符串。
// 之前把布尔值放在第 9 段、view 放在第 9 段，都会让 BlueMap 回退成透视视角。
const viewerSrc = computed(() => {
  if (!viewer.value || !activeMap.value) return ''
  const flat = viewMode.value === '2d'
  const [x, z] = startPos.value
  const distance = flat ? 1000 : 150
  const angle = flat ? 0 : 1.1
  const tilt = 0
  const ortho = flat ? 1 : 0
  const view = flat ? 'flat' : 'perspective'
  return `${viewer.value}#${activeMap.value}:${x}:${startY.value}:${z}:${distance}:0:${angle}:${tilt}:${ortho}:${view}`
})

function authHeaders() {
  return authState.token ? { Authorization: `Bearer ${authState.token}` } : {}
}

function showGate(code) {
  if (code === 'map_not_ready') {
    gate.value = { code, title: t('map.noViewer'), hint: t('map.noViewerHint'), action: '' }
    return
  }
  const membersOnly = code === 'map_members_only'
  gate.value = {
    code,
    title: membersOnly ? t('map.membersOnly') : t('map.error'),
    hint: membersOnly ? t('map.membersOnlyHint') : '',
    action: code === 'unauthorized' ? 'login' : membersOnly ? 'joinus' : '',
  }
}

// ---------- 沉浸模式：优先用浏览器全屏，Esc 由浏览器处理并回调 ----------
async function enterImmersive() {
  const el = wrapEl.value
  if (el?.requestFullscreen) {
    try {
      await el.requestFullscreen()
      immersive.value = true
      return
    } catch {
      // 没有用户手势等情况下退化为铺满视口
    }
  }
  immersive.value = true
}

async function exitImmersive() {
  if (document.fullscreenElement) {
    try {
      await document.exitFullscreen()
    } catch {
      // 忽略：下面统一复位状态
    }
  }
  immersive.value = false
}

function onFullscreenChange() {
  immersive.value = !!document.fullscreenElement
}

function onKeydown(e) {
  if (e.key === 'Escape' && immersive.value) exitImmersive()
}

function switchView(mode) {
  if (viewMode.value === mode) return
  viewMode.value = mode
  localStorage.setItem('whs_map_view', mode)
  if (mode === '3d') enterImmersive()
  else exitImmersive()
}

watch(immersive, (on) => {
  document.body.style.overflow = on ? 'hidden' : ''
})

watch(viewMode, () => {
  loaded.value = false
  failed.value = false
  frameKey.value += 1
  beginLoad()
})

// ---------- 加载状态 ----------
function beginLoad() {
  if (loadTimer) clearTimeout(loadTimer)
  loadTimer = setTimeout(() => {
    if (!loaded.value) failed.value = true
  }, 15000)
}

function onFrameLoad() {
  loaded.value = true
  failed.value = false
  if (loadTimer) clearTimeout(loadTimer)
  showControls.value = true
  if (controlsTimer) clearTimeout(controlsTimer)
  controlsTimer = setTimeout(() => { showControls.value = false }, 6000)
}

// ---------- 配置与玩家数 ----------
function scheduleRefresh(ttl) {
  if (configTimer) clearTimeout(configTimer)
  const wait = Math.max(((ttl || 600) - 120) * 1000, 60000)
  configTimer = setTimeout(refreshCookie, wait)
}

// 只刷新通行 Cookie，不重建 iframe，避免长时间挂机后画面反复重载
async function refreshCookie() {
  try {
    const res = await fetch('/api/map/config', { headers: authHeaders() })
    // 登录态失效时不能静默返回，否则画面会停在已经 401 的 iframe 上
    if (res.status === 401) {
      showGate('unauthorized')
      return
    }
    // 403 / 503 都是可恢复的，继续轮询，避免 Cookie 过期后永远不再续签
    if (!res.ok) {
      if (configTimer) clearTimeout(configTimer)
      configTimer = setTimeout(refreshCookie, 30000)
      return
    }
    const data = await res.json()
    scheduleRefresh(data.ttl)
  } catch {
    // 网络抖动时保留现有画面，30 秒后重试。
    // 不能沿用长间隔，否则拖到 Cookie 过期后 iframe 会静默停在错误页。
    if (configTimer) clearTimeout(configTimer)
    configTimer = setTimeout(refreshCookie, 30000)
  }
}

async function loadPlayers() {
  if (!activeMap.value || gate.value) return
  try {
    const res = await fetch(`/api/map/players?map_id=${encodeURIComponent(activeMap.value)}`, {
      headers: authHeaders(),
    })
    if (!res.ok) return
    const data = await res.json()
    playerCount.value = Number(data.count) || 0
  } catch {
    // 轮询失败不打扰用户
  }
}

async function loadConfig() {
  try {
    const res = await fetch('/api/map/config', { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showGate(data.code || 'error')
      return
    }
    gate.value = null
    available.value = true
    viewer.value = data.viewer || ''
    startY.value = Number(data.start_y) || 80
    maps.value = data.maps || []

    const target = data.maps?.find((m) => m.id === activeMap.value)
      || data.maps?.find((m) => m.id === data.default)
      || data.maps?.[0]
    if (!target) {
      showGate('error')
      return
    }
    activeMap.value = target.id
    startPos.value = target.start || [0, 0]
    loaded.value = false
    failed.value = false
    frameKey.value += 1
    beginLoad()
    scheduleRefresh(data.ttl)
    loadPlayers()
  } catch {
    if (!available.value) showGate('network')
    // 首次加载失败时自动重试，避免网络抖动后页面永远停在错误态
    if (configTimer) clearTimeout(configTimer)
    configTimer = setTimeout(loadConfig, 30000)
  } finally {
    loading.value = false
  }
}

async function onMapChange() {
  await loadConfig()
}

onMounted(() => {
  loadConfig()
  playersTimer = setInterval(loadPlayers, 15000)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  if (configTimer) clearTimeout(configTimer)
  if (playersTimer) clearInterval(playersTimer)
  if (loadTimer) clearTimeout(loadTimer)
  if (controlsTimer) clearTimeout(controlsTimer)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
})
</script>

<template>
  <Top_navbar />

  <main class="map-page">
    <header class="map-head">
      <div>
        <h1 class="map-title">{{ t('map.title') }}</h1>
        <p class="map-sub">{{ t('map.subtitle') }}</p>
      </div>
      <div class="map-tools">
        <div class="view-switch" role="group" :aria-label="t('map.view')">
          <span class="view-thumb" :class="{ 'is-3d': viewMode === '3d' }" aria-hidden="true"></span>
          <button
            type="button"
            class="view-btn"
            :class="{ active: viewMode === '2d' }"
            :aria-pressed="viewMode === '2d'"
            @click="switchView('2d')"
          >2D</button>
          <button
            type="button"
            class="view-btn"
            :class="{ active: viewMode === '3d' }"
            :aria-pressed="viewMode === '3d'"
            @click="switchView('3d')"
          >3D</button>
        </div>
        <select v-if="maps.length > 1" v-model="activeMap" class="map-select" @change="onMapChange">
          <option v-for="m in maps" :key="m.id" :value="m.id">{{ m.name }}</option>
        </select>
        <span class="map-count">{{ t('map.players') }} {{ playerCount }}</span>
      </div>
    </header>

    <div v-if="gate" class="map-gate">
      <h2 class="gate-title">{{ gate.title }}</h2>
      <p v-if="gate.hint" class="gate-hint">{{ gate.hint }}</p>
      <router-link v-if="gate.action === 'login'" class="gate-link" to="/login">{{ t('map.goLogin') }}</router-link>
      <router-link v-else-if="gate.action === 'joinus'" class="gate-link" to="/joinus">{{ t('map.goExam') }}</router-link>
    </div>

    <div
      v-show="!gate"
      ref="wrapEl"
      class="map-canvas-wrap"
      :class="{ 'is-immersive': immersive }"
    >
      <iframe
        v-if="available && viewer"
        :key="frameKey"
        ref="frameEl"
        :src="viewerSrc"
        class="map-frame"
        :title="t('map.title')"
        allow="fullscreen"
        allowfullscreen
        @load="onFrameLoad"
      ></iframe>

      <div v-else-if="loading" class="map-loading">{{ t('map.loading') }}</div>

      <div v-else class="map-tip">
        <p class="tip-title">{{ t('map.noViewer') }}</p>
        <p class="tip-hint">{{ t('map.noViewerHint') }}</p>
      </div>

      <div v-if="available && !loaded && !failed" class="map-loading">{{ t('map.loading') }}</div>
      <div v-if="failed" class="map-tip">
        <p class="tip-title">{{ t('map.errorViewer') }}</p>
      </div>

      <div v-if="immersive" class="immersive-bar">
        <button type="button" class="immersive-btn" @click="exitImmersive">
          {{ t('map.immersiveExit') }}
        </button>
      </div>
      <div v-else-if="available && loaded" class="immersive-bar">
        <button type="button" class="immersive-btn" @click="enterImmersive">
          {{ t('map.immersiveEnter') }}
        </button>
      </div>

      <div v-if="showControls && loaded" class="map-hint">
        {{ viewMode === '3d' ? t('map.controls3d') : t('map.controls2d') }}
      </div>
    </div>
  </main>

  <Page_footer />
</template>

<style scoped>
.map-page {
  padding: 72px 24px 48px;
  max-width: 1440px;
  margin: 0 auto;
  box-sizing: border-box;
}

.map-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.map-title {
  margin: 0 0 6px;
  font-size: 28px;
  font-weight: 800;
  color: var(--text-color, #1f2937);
}

.map-sub {
  margin: 0;
  font-size: 14px;
  color: var(--links-color, #6b7280);
}

.map-tools {
  display: flex;
  align-items: center;
  gap: 12px;
}

.map-select {
  padding: 8px 12px;
  border: 1px solid var(--float-bg);
  border-radius: 8px;
  background: transparent;
  color: var(--text-color, #1f2937);
  font: inherit;
}

.map-count {
  font-size: 14px;
  color: var(--links-color, #6b7280);
}

.map-canvas-wrap {
  position: relative;
  border: 1px solid var(--float-bg);
  border-radius: 12px;
  overflow: hidden;
  height: calc(100vh - 240px);
  min-height: 420px;
  background: #0f172a;
}

.map-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}

.map-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.55);
  color: #fff;
  font-size: 15px;
  pointer-events: none;
}

.map-tip {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  text-align: center;
}

.tip-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.tip-hint {
  margin: 0;
  font-size: 13px;
  color: #cbd5e1;
}

.map-gate {
  padding: 56px 24px;
  border: 1px solid var(--float-bg);
  border-radius: 12px;
  text-align: center;
}

.gate-title {
  margin: 0 0 10px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-color, #1f2937);
}

.gate-hint {
  margin: 0 0 18px;
  font-size: 14px;
  color: var(--links-color, #6b7280);
}

.gate-link {
  display: inline-block;
  padding: 10px 28px;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font-weight: 700;
  text-decoration: none;
}

/* 2D / 3D 分段切换：白色胶囊滑块跟随选中项滑动 */
.view-switch {
  position: relative;
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  background: var(--float-bg);
}

.view-btn {
  position: relative;
  z-index: 1;
  min-width: 52px;
  padding: 6px 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: color 0.24s ease;
}

.view-btn.active {
  color: var(--text-color);
}

.view-btn:focus-visible {
  outline: 2px solid var(--text-color);
  outline-offset: 1px;
}

.view-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: calc(50% - 3px);
  height: calc(100% - 6px);
  border-radius: 999px;
  background: var(--card-color);
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.16);
  transition: transform 0.32s cubic-bezier(0.22, 1, 0.36, 1);
}

.view-thumb.is-3d {
  transform: translateX(100%);
}

/* 浏览器全屏不可用时的退路：铺满视口 */
.map-canvas-wrap.is-immersive {
  position: fixed;
  inset: 0;
  z-index: 2000;
  height: 100%;
  min-height: 0;
  border: none;
  border-radius: 0;
}

.immersive-bar {
  position: absolute;
  top: 18px;
  right: 18px;
  z-index: 3;
}

.immersive-btn {
  padding: 9px 18px;
  border: none;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.72);
  color: #fff;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  backdrop-filter: blur(10px);
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.immersive-btn:hover {
  background: rgba(15, 23, 42, 0.92);
}

.immersive-btn:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

.map-hint {
  position: absolute;
  left: 50%;
  bottom: 28px;
  z-index: 3;
  padding: 10px 20px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.72);
  color: #e2e8f0;
  font-size: 13px;
  white-space: nowrap;
  backdrop-filter: blur(10px);
  animation: hint-in 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes hint-in {
  from {
    opacity: 0;
    transform: translate(-50%, 10px);
  }
  to {
    opacity: 1;
    transform: translate(-50%, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .map-hint {
    animation: none;
    transform: translateX(-50%);
  }

  .view-thumb {
    transition: none;
  }
}

@media (max-width: 768px) {
  .map-page {
    padding: 60px 12px 32px;
  }

  .map-title {
    font-size: 22px;
  }

  .map-canvas-wrap {
    height: calc(100vh - 280px);
  }

  .map-hint {
    width: calc(100% - 32px);
    box-sizing: border-box;
    text-align: center;
    white-space: normal;
  }

  .immersive-bar {
    top: 12px;
    right: 12px;
  }
}
</style>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { Maximize2, Minimize2, Users, Map as MapIcon, Route } from 'lucide-vue-next'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import StatusDropdown from '../components/status_dropdown.vue'
import { useAuth } from '../composables/useAuth'

const { t } = useI18n()
const { state: authState } = useAuth()
const route = useRoute()
const router = useRouter()

const wrapEl = ref(null)
const frameEl = ref(null)
const maps = ref([])
const activeMap = ref('')
const playerCount = ref(0)
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
// 地图变化时重建 iframe，让 BlueMap 按新的地图/出生点初始化
const frameKey = ref(0)
// 从路线图跳转过来时的临时视角覆盖（/map?x=&z=&y=&station=）
const focusTarget = ref(null)
const pendingFocus = ref(readFocusQuery())

let configTimer = null
let playersTimer = null
let loadTimer = null
let controlsTimer = null

// BlueMap 5.x 的 hash：mapId:x:y:z:distance:rotation:angle:tilt:ortho:view
// 地图页固定使用 3D 透视视图；视角贴近地表并略微压低，接近游戏内旁观。
const viewerSrc = computed(() => {
  if (!viewer.value || !activeMap.value) return ''
  const focus = focusTarget.value
  const mapId = focus?.map || activeMap.value
  const [x, z] = focus ? [focus.x, focus.z] : startPos.value
  const y = focus ? focus.y : startY.value + 20
  // 从路线图定位时拉近视角，默认仍是出生点上方的广角
  const distance = focus ? 60 : 150
  return `${viewer.value}#${mapId}:${x}:${y}:${z}:${distance}:0:1.1:0:0:perspective`
})

// 站点通用下拉组件（status_dropdown.vue）的选项格式
const mapOptions = computed(() => maps.value.map((m) => ({ value: m.id, label: m.name })))

function readFocusQuery() {
  const x = Number(route.query.x)
  const z = Number(route.query.z)
  if (!Number.isFinite(x) || !Number.isFinite(z)) return null
  const y = Number(route.query.y)
  return { x, z, y: Number.isFinite(y) ? y : null, station: String(route.query.station || '') }
}

/** 从路线图点站进来：把视角落到该坐标，并清掉 query（一次性消费）。 */
function applyPendingFocus() {
  const target = pendingFocus.value
  if (!target) return
  pendingFocus.value = null
  focusTarget.value = {
    map: activeMap.value,
    x: target.x,
    z: target.z,
    y: (target.y ?? startY.value) + 20,
  }
  loaded.value = false
  failed.value = false
  frameKey.value += 1
  beginLoad()
  router.replace({ path: '/map' })
}

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

watch(immersive, (on) => {
  document.body.style.overflow = on ? 'hidden' : ''
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
    applyPendingFocus()
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
  // 手动切地图时丢掉路线图的定位覆盖，回到新地图的出生点
  focusTarget.value = null
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
      <div class="map-heading">
        <span class="map-eyebrow">
          <span class="map-eyebrow-dot" aria-hidden="true"></span>
          {{ t('map.eyebrow') }}
        </span>
        <h1 class="map-title">{{ t('map.title') }}</h1>
        <p class="map-sub">{{ t('map.subtitle') }}</p>
      </div>

      <div class="map-tools">
        <span class="map-live">
          <Users :size="15" aria-hidden="true" />
          {{ t('map.players') }}
          <strong>{{ playerCount }}</strong>
        </span>

        <StatusDropdown
          v-if="maps.length > 1"
          v-model="activeMap"
          :options="mapOptions"
          variant="select"
          class="map-select"
          :aria-label="t('map.title')"
          @update:model-value="onMapChange"
        >
          <template #prefix>
            <MapIcon :size="15" class="map-select-icon" aria-hidden="true" />
          </template>
        </StatusDropdown>


        <button
          v-if="available && loaded && !immersive"
          type="button"
          class="map-fullscreen"
          @click="enterImmersive"
        >
          <Maximize2 :size="16" aria-hidden="true" />
          <span>{{ t('map.immersiveEnter') }}</span>
        </button>
      </div>
    </header>

    <div v-if="!immersive" class="map-transit-notice">
      <Route :size="15" aria-hidden="true" />
      <span>{{ t('map.transitNotice') }}</span>
      <router-link to="/map/transit">{{ t('map.transitNoticeLink') }}</router-link>
    </div>

    <div v-if="gate" class="map-gate">
      <span class="gate-icon" aria-hidden="true"><MapIcon :size="28" /></span>
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

      <div v-if="available && !loaded && !failed" class="map-loading">
        <span class="map-spinner" aria-hidden="true"></span>
        <span>{{ t('map.loading') }}</span>
      </div>
      <div v-else-if="!available && loading" class="map-loading">
        <span class="map-spinner" aria-hidden="true"></span>
        <span>{{ t('map.loading') }}</span>
      </div>

      <div v-if="failed" class="map-tip">
        <p class="tip-title">{{ t('map.errorViewer') }}</p>
      </div>
      <div v-else-if="!available && !loading && !gate" class="map-tip">
        <p class="tip-title">{{ t('map.noViewer') }}</p>
        <p class="tip-hint">{{ t('map.noViewerHint') }}</p>
      </div>

      <div v-if="immersive" class="immersive-bar">
        <button type="button" class="immersive-btn" @click="exitImmersive">
          <Minimize2 :size="16" aria-hidden="true" />
          <span>{{ t('map.immersiveExit') }}</span>
        </button>
      </div>

      <div v-if="showControls && loaded" class="map-hint">
        {{ t('map.controls3d') }}
      </div>
    </div>

  </main>

  <Page_footer />
</template>

<style scoped>
.map-page {
  position: relative;
  isolation: isolate;
  margin: 0 auto;
  padding: 88px 28px 56px;
  box-sizing: border-box;
}

.map-page::before {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0;
  pointer-events: none;
}

.map-head {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.map-heading {
  min-width: 0;
}

.map-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: #a16207;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.map-eyebrow-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.13);
}

.map-title {
  margin: 0;
  color: var(--text-color, #1f2937);
  font-size: clamp(30px, 4.1vw, 46px);
  font-weight: 800;
  letter-spacing: -0.035em;
  line-height: 1.05;
}

.map-sub {
  max-width: 680px;
  margin: 12px 0 0;
  color: var(--links-color, #6b7280);
  font-size: 15px;
  line-height: 1.7;
}

.map-transit-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 0 0 12px;
  padding: 9px 14px;
  font-size: 13px;
  color: var(--links-color);
  background: var(--card-color);
  border: 1px solid var(--float-bg);
  border-radius: 12px;
}

.map-transit-notice svg {
  color: var(--notice-color);
}

.map-transit-notice a {
  margin-left: auto;
  font-weight: 700;
  color: var(--text-color);
  text-decoration: none;
}

.map-transit-notice a:hover {
  color: var(--notice-color);
}

.map-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-left: auto;
}

.map-live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 40px;
  padding: 0 13px;
  box-sizing: border-box;
  border: 1px solid var(--float-bg);
  border-radius: 12px;
  background: var(--card-color);
  color: var(--links-color);
  font-size: 13px;
  white-space: nowrap;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
}

.map-live svg {
  color: #22c55e;
}

.map-live strong {
  color: var(--text-color);
  font-size: 15px;
  font-weight: 800;
}

/* 地图选择：使用站点通用下拉组件（status_dropdown.vue，variant=select） */
.map-select {
  max-width: 100%;
}

.map-select :deep(.sd-btn) {
  max-width: 260px;
}

.map-select-icon {
  flex-shrink: 0;
  color: var(--links-color);
}

.map-fullscreen {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 16px;
  border: 0;
  border-radius: 12px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(235, 170, 40, 0.18);
  transition: transform 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.map-fullscreen:hover {
  background: #f0b438;
  box-shadow: 0 8px 22px rgba(235, 170, 40, 0.25);
  transform: translateY(-1px);
}

.map-fullscreen:active {
  transform: translateY(0);
}

.map-fullscreen:focus-visible {
  outline: 2px solid var(--text-color);
  outline-offset: 3px;
}


.map-canvas-wrap {
  position: relative;
  height: calc(100vh - 250px);
  min-height: 480px;
  max-height: 860px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 0%, rgba(59, 130, 246, 0.12), transparent 42%),
    #0b1220;
  box-shadow:
    0 30px 80px rgba(15, 23, 42, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.07);
}

.map-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  background: #0b1220;
}

.map-loading {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(8, 15, 28, 0.76);
  color: #f8fafc;
  font-size: 14px;
  letter-spacing: 0.02em;
  pointer-events: none;
}

.map-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.22);
  border-top-color: #ebaa28;
  border-radius: 50%;
  animation: map-spin 0.8s linear infinite;
}

@keyframes map-spin {
  to { transform: rotate(360deg); }
}

.map-tip {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  text-align: center;
  background: radial-gradient(circle at center, rgba(30, 41, 59, 0.6), rgba(8, 15, 28, 0.92));
}

.tip-title {
  margin: 0;
  color: #f8fafc;
  font-size: 17px;
  font-weight: 800;
}

.tip-hint {
  max-width: 440px;
  margin: 0;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.7;
}

.map-gate {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 64px 24px;
  border: 1px solid var(--float-bg);
  border-radius: 22px;
  background:
    radial-gradient(circle at 50% 0%, rgba(235, 170, 40, 0.08), transparent 46%),
    var(--card-color);
  text-align: center;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
}

.gate-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin-bottom: 4px;
  border-radius: 18px;
  background: rgba(235, 170, 40, 0.13);
  color: #a16207;
}

.gate-title {
  margin: 0;
  color: var(--text-color);
  font-size: 23px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.gate-hint {
  max-width: 520px;
  margin: 0;
  color: var(--links-color);
  font-size: 14px;
  line-height: 1.7;
}

.gate-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  margin-top: 8px;
  padding: 0 24px;
  border-radius: 11px;
  background: #ebaa28;
  color: #1f2937;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none;
  transition: background-color 0.2s ease, transform 0.2s ease;
}

.gate-link:hover {
  background: #f0b438;
  transform: translateY(-1px);
}

.map-fullscreen:focus-visible,
.gate-link:focus-visible {
  outline: 2px solid var(--text-color);
  outline-offset: 3px;
}

/* 浏览器全屏不可用时的退路：铺满视口 */
.map-canvas-wrap.is-immersive {
  position: fixed;
  inset: 0;
  z-index: 2000;
  height: 100%;
  min-height: 0;
  max-height: none;
  border: none;
  border-radius: 0;
}

.immersive-bar {
  position: absolute;
  left: 22px;
  bottom: 22px;
  z-index: 6;
}

.immersive-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 11px;
  background: rgba(8, 15, 28, 0.78);
  color: #f8fafc;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.immersive-btn:hover {
  border-color: rgba(255, 255, 255, 0.3);
  background: rgba(8, 15, 28, 0.92);
}

.immersive-btn:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

.map-hint {
  position: absolute;
  left: 50%;
  bottom: 24px;
  z-index: 5;
  max-width: calc(100% - 200px);
  box-sizing: border-box;
  padding: 10px 18px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  background: rgba(8, 15, 28, 0.78);
  color: #e2e8f0;
  font-size: 13px;
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
  pointer-events: none;
  backdrop-filter: blur(10px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
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

:global(html.dark) .map-eyebrow {
  color: #f0b860;
}

:global(html.dark) .map-canvas-wrap {
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow:
    0 30px 80px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

:global(html.dark) .gate-icon {
  color: #f0b860;
}

@media (prefers-reduced-motion: reduce) {
  .map-hint {
    animation: none;
    transform: translateX(-50%);
  }

  .map-spinner {
    animation: none;
  }
}

@media (max-width: 900px) {
  .map-page {
    padding: 76px 18px 40px;
  }

  .map-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 18px;
  }

  .map-tools {
    width: 100%;
    justify-content: flex-start;
    margin-left: 0;
  }

  .map-canvas-wrap {
    height: calc(100vh - 300px);
    min-height: 400px;
  }
}

@media (max-width: 560px) {
  .map-page {
    padding: 60px 12px 32px;
  }

  .map-title {
    font-size: 29px;
  }

  .map-sub {
    font-size: 14px;
  }

  .map-tools {
    gap: 8px;
  }

  .map-live,
  .map-fullscreen {
    min-height: 38px;
  }

  .map-select :deep(.sd-btn) {
    height: 38px;
  }

  .map-fullscreen {
    padding: 0 13px;
  }

  .map-canvas-wrap {
    height: calc(100vh - 340px);
    min-height: 340px;
    border-radius: 16px;
  }

  .map-hint {
    width: calc(100% - 32px);
    max-width: none;
    bottom: 16px;
    text-align: center;
    white-space: normal;
    border-radius: 12px;
  }

  .immersive-bar {
    left: 12px;
    bottom: 12px;
  }

  .gate-title {
    font-size: 20px;
  }
}
</style>

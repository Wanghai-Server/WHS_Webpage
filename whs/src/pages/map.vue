<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import Top_navbar from '../components/top_navbar.vue'
import Page_footer from '../components/page_footer.vue'
import { useAuth } from '../composables/useAuth'

const { t } = useI18n()
const { state: authState } = useAuth()

const mapEl = ref(null)
const maps = ref([])
const activeMap = ref('')
const players = ref([])
// 2D / 3D 视图切换，记住上次选择
const viewMode = ref(localStorage.getItem('whs_map_view') === '3d' ? '3d' : '2d')
const viewer = ref('')
const viewerStarted = ref(false)
const viewerReady = ref(false)
const viewerFailed = ref(false)
const gate = ref(null) // 非空时展示提示卡片（未登录 / 非正式成员 / 服务异常）
const loading = ref(true)

let leafletMap = null
let tileLayer = null
let playerLayer = null
let configTimer = null
let playersTimer = null
let viewerTimer = null
// 当前地图的瓦片参数（来自 BlueMap settings.json）
let geo = null
let tileBase = ''
let currentMapId = ''

// BlueMap 的瓦片按 lod 分层：lod 0 是最高清的一层（hires），
// lod 1..n 是逐级缩小的 lowres，每级相差 lodFactor 倍。
// 这里让 Leaflet 的 zoom 直接用 lodFactor 进制，zoom 0 = lod 0，zoom -1 = lod 1……
function buildCrs(lodFactor, translate) {
  return L.Util.extend({}, L.CRS.Simple, {
    scale: (zoom) => Math.pow(lodFactor, zoom),
    zoom: (scale) => Math.log(scale) / Math.log(lodFactor),
    transformation: new L.Transformation(1, translate, 1, translate),
  })
}

function buildLayer(tileSize, lodForZoom) {
  const Layer = L.GridLayer.extend({
    createTile(coords) {
      const img = document.createElement('img')
      img.alt = ''
      img.draggable = false
      const lod = lodForZoom(coords.z)
      if (lod === null) {
        img.style.visibility = 'hidden'
        return img
      }
      img.src = tileBase
        .replace('{lod}', lod)
        .replace('{x}', coords.x)
        .replace('{y}', coords.y)
      img.onerror = () => { img.style.visibility = 'hidden' }
      return img
    },
  })
  return new Layer({ tileSize, noWrap: true, updateWhenIdle: false })
}

// 根据 zoom 在 hires / lowres 两层之间切换
function syncLayer() {
  if (!leafletMap || !geo) return
  const zoom = leafletMap.getZoom()
  const wantLow = zoom < 0
  const current = tileLayer
  const next = wantLow ? geo.lowLayer : geo.hiresLayer
  if (current === next) return
  if (current) leafletMap.removeLayer(current)
  next.addTo(leafletMap)
  tileLayer = next
}

function setupMap(info) {
  const s = info.settings || {}
  const lodFactor = s.lowres?.lodFactor || 5
  const hiresSize = s.hires?.tileSize || 32
  const lowSize = s.lowres?.tileSize || 500
  const translate = s.hires?.translate || 0
  const lodCount = s.lowres?.lodCount || 0
  const start = s.startPos || [0, 0]

  geo = {
    hiresLayer: buildLayer(hiresSize, () => 0),
    lowLayer: buildLayer(lowSize, (z) => (z < 0 ? -z : null)),
    lodFactor,
  }

  leafletMap = L.map(mapEl.value, {
    crs: buildCrs(lodFactor, translate),
    minZoom: -Math.max(lodCount, 0),
    maxZoom: 0,
    zoomSnap: 1,
    zoomDelta: 1,
    attributionControl: false,
    zoomControl: true,
    worldCopyJump: false,
  })

  playerLayer = L.layerGroup().addTo(leafletMap)

  // Minecraft 的 z 轴向南为正，与 Leaflet 的纬度方向一致：latLng(z, x)
  leafletMap.setView([info.center?.[1] ?? start[1] ?? 0, info.center?.[0] ?? start[0] ?? 0],
    info.zoom ?? 0)

  tileLayer = geo.hiresLayer.addTo(leafletMap)
  syncLayer()
  leafletMap.on('zoomend', syncLayer)
}

function renderPlayers(list) {
  if (!playerLayer) return
  playerLayer.clearLayers()
  list.forEach((p) => {
    const pos = p.position || p.pos
    if (!pos || typeof pos.x !== 'number' || typeof pos.z !== 'number') return
    const marker = L.circleMarker([pos.z, pos.x], {
      radius: 6,
      color: '#ffffff',
      weight: 2,
      fillColor: '#ebaa28',
      fillOpacity: 1,
    })
    if (p.name) marker.bindTooltip(p.name, { direction: 'top', offset: [0, -6] })
    marker.addTo(playerLayer)
  })
}

// 3D 视图由 BlueMap webapp 自己渲染，这里只传地图 id，视角交给它自己的 startPos
const viewerSrc = computed(() => `${viewer.value}#${activeMap.value}`)

function startViewer() {
  if (viewerStarted.value) return
  viewerStarted.value = true
  viewerReady.value = false
  viewerFailed.value = false
  if (viewerTimer) clearTimeout(viewerTimer)
  // 跨源 iframe 无法可靠捕获加载失败，用超时兜底
  viewerTimer = setTimeout(() => {
    if (!viewerReady.value) viewerFailed.value = true
  }, 15000)
}

function onViewerLoad() {
  viewerReady.value = true
  if (viewerTimer) clearTimeout(viewerTimer)
}

function switchView(mode) {
  if (viewMode.value === mode) return
  viewMode.value = mode
  localStorage.setItem('whs_map_view', mode)
  if (mode === '3d' && viewer.value) startViewer()
}

watch(viewMode, async (mode) => {
  // 2D 容器在 3D 模式下是 display:none，切回来需要重新计算尺寸
  if (mode === '2d' && leafletMap) {
    await nextTick()
    leafletMap.invalidateSize()
  }
})

function authHeaders() {
  return authState.token ? { Authorization: `Bearer ${authState.token}` } : {}
}

async function loadPlayers() {
  if (!activeMap.value || gate.value) return
  try {
    const res = await fetch(`/api/map/players?map_id=${encodeURIComponent(activeMap.value)}`, {
      headers: authHeaders(),
    })
    if (!res.ok) return
    const data = await res.json()
    players.value = Array.isArray(data.players) ? data.players : []
    renderPlayers(players.value)
  } catch {
    // 轮询失败不打扰用户，下一轮再试
  }
}

function destroyMap() {
  if (leafletMap) {
    leafletMap.remove()
    leafletMap = null
    tileLayer = null
    playerLayer = null
  }
}

function showGate(code) {
  const membersOnly = code === 'map_members_only'
  gate.value = {
    code,
    title: membersOnly ? t('map.membersOnly') : t('map.error'),
    hint: membersOnly ? t('map.membersOnlyHint') : '',
    action: code === 'unauthorized' ? 'login' : membersOnly ? 'joinus' : '',
  }
  destroyMap()
  currentMapId = ''
}

async function loadConfig({ rebuild = false } = {}) {
  if (!leafletMap) loading.value = true
  try {
    const res = await fetch('/api/map/config', { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showGate(data.code || 'error')
      return
    }
    gate.value = null
    maps.value = data.maps || []
    // 续签时保持当前选中的地图，只有首次进入或手动切换才回落到默认地图
    const target = data.maps?.find((m) => m.id === activeMap.value)
      || data.maps?.find((m) => m.id === data.default)
      || data.maps?.[0]
    if (!target) {
      showGate('empty')
      return
    }
    activeMap.value = target.id
    tileBase = target.tile
    viewer.value = data.viewer || ''
    if (viewMode.value === '3d' && viewer.value) startViewer()
    if (rebuild || currentMapId !== target.id) {
      currentMapId = target.id
      destroyMap()
      await nextTick()
      setupMap(target)
    } else if (tileLayer) {
      // 令牌已换新，让已加载的瓦片用新地址重新请求
      tileLayer.redraw()
    }

    if (configTimer) clearTimeout(configTimer)
    const wait = Math.max((data.refetch_after || 300) * 1000, 60000)
    configTimer = setTimeout(loadConfig, wait)

    loadPlayers()
  } catch {
    // 已有地图时遇到网络抖动不销毁画面，等下次续签重试
    if (!leafletMap) showGate('network')
  } finally {
    loading.value = false
  }
}

async function onMapChange() {
  await loadConfig({ rebuild: true })
}

onMounted(() => {
  loadConfig()
  playersTimer = setInterval(loadPlayers, 15000)
})

onBeforeUnmount(() => {
  if (configTimer) clearTimeout(configTimer)
  if (playersTimer) clearInterval(playersTimer)
  if (viewerTimer) clearTimeout(viewerTimer)
  destroyMap()
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
          <option v-for="m in maps" :key="m.id" :value="m.id">{{ m.id }}</option>
        </select>
        <span class="map-count">{{ t('map.players') }} {{ players.length }}</span>
      </div>
    </header>

    <div v-if="gate" class="map-gate">
      <h2 class="gate-title">{{ gate.title }}</h2>
      <p v-if="gate.hint" class="gate-hint">{{ gate.hint }}</p>
      <router-link v-if="gate.action === 'login'" class="gate-link" to="/login">{{ t('map.goLogin') }}</router-link>
      <router-link v-else-if="gate.action === 'joinus'" class="gate-link" to="/joinus">{{ t('map.goExam') }}</router-link>
    </div>

    <div v-show="!gate" class="map-canvas-wrap">
      <div v-show="viewMode === '2d'" ref="mapEl" class="map-canvas"></div>

      <div v-show="viewMode === '3d'" class="map-3d">
        <iframe
          v-if="viewerStarted && viewer"
          :src="viewerSrc"
          class="map-3d-frame"
          title="3D map"
          allowfullscreen
          @load="onViewerLoad"
        ></iframe>
        <div v-else class="map-3d-tip">
          <p class="tip-title">{{ t('map.no3d') }}</p>
          <p class="tip-hint">{{ t('map.no3dHint') }}</p>
        </div>
        <div v-if="viewerStarted && viewer && !viewerReady && !viewerFailed" class="map-loading">
          {{ t('map.loading3d') }}
        </div>
        <div v-if="viewerFailed" class="map-3d-tip">
          <p class="tip-title">{{ t('map.error3d') }}</p>
        </div>
      </div>

      <div v-if="viewMode === '2d' && loading" class="map-loading">{{ t('map.loading') }}</div>
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
}

.map-canvas {
  height: calc(100vh - 240px);
  min-height: 420px;
  width: 100%;
  background: #0f172a;
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

.map-3d {
  position: relative;
  height: calc(100vh - 240px);
  min-height: 420px;
  background: #0f172a;
}

.map-3d-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}

.map-3d-tip {
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

@media (prefers-reduced-motion: reduce) {
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

  .map-canvas {
    height: calc(100vh - 280px);
  }

  .map-3d {
    height: calc(100vh - 280px);
  }
}
</style>

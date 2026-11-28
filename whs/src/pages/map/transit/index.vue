<script setup>
/**
 * 轨交路线图（/map/transit，公开只读）。
 *
 * - 数据来自 GET /api/map/transit（当前版本）；
 * - 渲染用 SVG 示意图（components/transit_diagram.vue）；
 * - 点车站出卡片，可跳到 /map?x=&z=&y=&station= 让 BlueMap 定位；
 * - 与 BlueMap 页面互相独立：这里不加载 BlueMap。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Pencil, Route, Search, MapPin } from 'lucide-vue-next'
import Top_navbar from '../../../components/top_navbar.vue'
import Page_footer from '../../../components/page_footer.vue'
import TransitDiagram from '../../../components/transit_diagram.vue'
import MarkdownView from '../../../components/markdown_view.vue'
import { useAuth } from '../../../composables/useAuth'
import { buildSchematic, lineName, matchStations, stationName } from '../../../composables/transitLayout'

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()

const loading = ref(true)
const payload = ref(null)
const error = ref('')
const hiddenLines = ref([])
const keyword = ref('')
const selectedId = ref('')
const selectedLineId = ref('')

const data = computed(() => payload.value?.data || null)
const schematic = computed(() => (data.value ? buildSchematic(data.value, { locale: locale.value }) : null))
const stations = computed(() => schematic.value?.stations || [])
const lines = computed(() => schematic.value?.lines || [])
const selected = computed(() => stations.value.find((item) => item.id === selectedId.value) || null)
const selectedLineInfo = computed(() => lines.value.find((item) => item.id === selectedLineId.value) || null)
const diagramSelectedId = computed(() => selectedId.value || selectedLineId.value)
const matches = computed(() => matchStations(stations.value, keyword.value).slice(0, 6))
const canView3d = computed(() => (authState.user?.permission ?? 0) >= 2)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/map/transit', { headers: authHeaders() })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(body.code || 'http')
    payload.value = body
    if (!body.available) error.value = body.error || t('transit.unavailable')
  } catch {
    error.value = t('transit.loadFailed')
  } finally {
    loading.value = false
  }
}

function authHeaders() {
  return authState.token ? { Authorization: `Bearer ${authState.token}` } : {}
}

function onSelect({ kind, id }) {
  if (kind === 'line') {
    selectedLineId.value = id
    selectedId.value = ''
    return
  }
  selectedId.value = id
  selectedLineId.value = ''
}

function clearSelection() {
  selectedId.value = ''
  selectedLineId.value = ''
}

function lineStatusLabel(line) {
  if (line.status === 'building') return t('transit.edit.statusBuilding')
  if (line.status === 'planned') return t('transit.edit.statusPlanned')
  return t('transit.edit.statusOpen')
}

function stationsOfLine(line) {
  return (line.stations || [])
    .map((id) => stations.value.find((item) => item.id === id))
    .filter(Boolean)
}

function toggleLine(id) {
  const index = hiddenLines.value.indexOf(id)
  if (index >= 0) hiddenLines.value.splice(index, 1)
  else hiddenLines.value.push(id)
}

function selectStation(station) {
  selectedId.value = station.id
  selectedLineId.value = ''
}

function pickMatch(station) {
  selectedId.value = station.id
  selectedLineId.value = ''
  keyword.value = ''
}

function viewIn3d() {
  if (!selected.value) return
  router.push({
    path: '/map',
    query: {
      x: selected.value.pos[0],
      z: selected.value.pos[1],
      y: selected.value.y,
      station: selected.value.id,
    },
  })
}

onMounted(load)
</script>

<template>
  <Top_navbar />

  <main class="transit-page">
    <header class="transit-head">
      <div class="head-main">
        <span class="transit-eyebrow">
          <Route :size="15" aria-hidden="true" />
          {{ t('transit.eyebrow') }}
        </span>
        <h1 class="transit-title">{{ t('transit.title') }}</h1>
        <p class="transit-sub">{{ t('transit.subtitle') }}</p>
      </div>

      <div class="head-meta">
        <span v-if="payload?.sample" class="transit-badge">{{ t('transit.sample') }}</span>
        <span v-if="payload?.version" class="transit-version">v{{ payload.version }}</span>
        <span v-if="payload?.updated_at" class="transit-updated">
          {{ t('transit.updated', { date: String(payload.updated_at).slice(0, 10) }) }}
        </span>
        <RouterLink v-if="payload?.can_edit" to="/map/transit/edit" class="transit-edit">
          <Pencil :size="14" aria-hidden="true" />
          {{ t('transit.editEntry') }}
        </RouterLink>
      </div>
    </header>

    <div v-if="loading" class="transit-state">
      <span class="transit-spinner" aria-hidden="true"></span>
      <span>{{ t('transit.loading') }}</span>
    </div>

    <div v-else-if="error" class="transit-state">
      <p>{{ error }}</p>
      <button type="button" class="transit-retry" @click="load">{{ t('transit.retry') }}</button>
    </div>

    <template v-else>
      <div class="transit-toolbar">
        <label class="transit-search">
          <Search :size="14" aria-hidden="true" />
          <input v-model="keyword" type="search" :placeholder="t('transit.search')" :aria-label="t('transit.search')" />
        </label>

        <ul v-if="matches.length" class="transit-matches">
          <li v-for="item in matches" :key="item.id">
            <button type="button" @click="pickMatch(item)">{{ stationName(item, locale) }}</button>
          </li>
        </ul>

        <div class="transit-legend" role="group" :aria-label="t('transit.legend')">
          <button
            v-for="line in lines"
            :key="line.id"
            type="button"
            class="legend-chip"
            :class="{ 'is-off': hiddenLines.includes(line.id) }"
            @click="toggleLine(line.id)"
          >
            <span
              class="legend-line"
              :class="{ 'is-dashed': line.status !== 'open' }"
              :style="{ background: line.status === 'open' ? line.color : 'transparent', borderColor: line.color }"
              aria-hidden="true"
            ></span>
            {{ lineName(line, locale) }}
          </button>
        </div>
      </div>

      <div class="transit-canvas">
        <TransitDiagram
          :schematic="schematic"
          :selected-id="diagramSelectedId"
          :hidden-lines="hiddenLines"
          :locale="locale"
          @select="onSelect"
        />

        <aside v-if="selected" class="transit-card">
          <button type="button" class="card-close" :aria-label="t('transit.close')" @click="clearSelection">×</button>
          <h2>{{ stationName(selected, locale) }}</h2>
          <p class="card-coord">
            <MapPin :size="13" aria-hidden="true" />
            X {{ selected.pos[0] }} / Z {{ selected.pos[1] }}
          </p>
          <ul class="card-lines">
            <li v-for="id in selected.lines" :key="id">
              <span class="card-dot" :style="{ background: lines.find((item) => item.id === id)?.color }" aria-hidden="true"></span>
              {{ lineName(lines.find((item) => item.id === id) || {}, locale) }}
            </li>
          </ul>
          <MarkdownView v-if="selected.note" :content="selected.note" class="card-note" />

          <button v-if="canView3d" type="button" class="card-action" @click="viewIn3d">
            {{ t('transit.viewIn3d') }}
          </button>
          <RouterLink v-else to="/joinus" class="card-hint">{{ t('transit.needMember') }}</RouterLink>
        </aside>

        <aside v-else-if="selectedLineInfo" class="transit-card">
          <button type="button" class="card-close" :aria-label="t('transit.close')" @click="clearSelection">×</button>
          <h2>{{ lineName(selectedLineInfo, locale) }}</h2>
          <p class="card-coord">
            <span class="card-line-swatch" :style="{ background: selectedLineInfo.color }" aria-hidden="true"></span>
            {{ lineStatusLabel(selectedLineInfo) }}
          </p>
          <ol class="card-stations">
            <li v-for="station in stationsOfLine(selectedLineInfo)" :key="station.id">
              <button type="button" @click="selectStation(station)">{{ stationName(station, locale) }}</button>
            </li>
          </ol>
          <MarkdownView v-if="selectedLineInfo.note" :content="selectedLineInfo.note" class="card-note" />
        </aside>
      </div>

      <footer class="transit-foot">
        <span>{{ (schematic?.note && (schematic.note[locale] || schematic.note.zh)) || t('transit.schematic') }}</span>
        <RouterLink to="/map" class="transit-back">← {{ t('transit.backToMap') }}</RouterLink>
      </footer>
    </template>
  </main>

  <Page_footer />
</template>

<style scoped>
.transit-page {
  max-width: 1180px;
  margin: 0 auto;
  /* 顶部留出固定导航胶囊的高度，避免标题被盖住 */
  padding: 84px 20px 56px;
}

.transit-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.transit-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--links-color);
  text-transform: uppercase;
}

.transit-title {
  margin: 6px 0 4px;
  font-size: 30px;
  font-weight: 800;
}

.transit-sub {
  margin: 0;
  font-size: 14px;
  color: var(--links-color);
}

.head-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--links-color);
}

.transit-badge {
  padding: 3px 9px;
  color: var(--notice-color);
  border: 1px solid var(--notice-color);
  border-radius: 999px;
}

.transit-version {
  padding: 3px 8px;
  background: var(--float-bg);
  border-radius: 999px;
  font-family: ui-monospace, Menlo, monospace;
}

.transit-edit {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 34px;
  padding: 0 12px;
  box-sizing: border-box;
  color: var(--text-color);
  text-decoration: none;
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 9px;
}

.transit-edit:hover {
  background: var(--float-bg);
}

.transit-toolbar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.transit-search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 11px;
  box-sizing: border-box;
  color: var(--links-color);
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 10px;
}

.transit-search input {
  width: 170px;
  font-size: 13px;
  color: var(--text-color);
  background: transparent;
  border: 0;
  outline: none;
}

.transit-matches {
  position: absolute;
  top: 44px;
  left: 0;
  z-index: 5;
  width: 210px;
  margin: 0;
  padding: 4px;
  list-style: none;
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 10px;
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
}

.transit-matches button {
  width: 100%;
  padding: 7px 9px;
  font-size: 13px;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 7px;
}

.transit-matches button:hover {
  background: var(--float-bg);
}

.transit-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}

.legend-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  box-sizing: border-box;
  font-size: 12px;
  color: inherit;
  cursor: pointer;
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.1);
  border-radius: 999px;
}

.legend-chip.is-off {
  opacity: 0.4;
  text-decoration: line-through;
}

.legend-line {
  display: inline-block;
  width: 18px;
  height: 5px;
  border-radius: 3px;
}

.legend-line.is-dashed {
  height: 0;
  border-top: 3px dashed;
  border-radius: 0;
}

.transit-canvas {
  position: relative;
  height: min(68vh, 640px);
  border: 1px solid rgba(var(--text-color-rgb), 0.1);
  border-radius: 16px;
  overflow: hidden;
}

.transit-card {
  position: absolute;
  top: 14px;
  left: 14px;
  width: 250px;
  padding: 14px 16px;
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 13px;
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.2);
}

.transit-card h2 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 700;
}

.card-close {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 26px;
  height: 26px;
  font-size: 16px;
  line-height: 1;
  color: var(--links-color);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 7px;
}

.card-close:hover {
  background: var(--float-bg);
}

.card-coord {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--links-color);
}

.card-lines {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.card-lines li {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--links-color);
}

.card-dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.card-note {
  margin: 9px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--links-color);
}

.card-note :deep(.md-body) {
  font-size: 12px;
}

.card-line-swatch {
  display: inline-block;
  width: 18px;
  height: 5px;
  border-radius: 3px;
}

.card-stations {
  margin: 9px 0 0;
  padding: 0 0 0 18px;
  font-size: 12px;
  color: var(--links-color);
}

.card-stations li {
  margin-top: 3px;
}

.card-stations button {
  padding: 0;
  font-size: 12px;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.card-stations button:hover {
  color: var(--text-color);
}

.card-action {
  width: 100%;
  margin-top: 11px;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 700;
  color: #1f2937;
  cursor: pointer;
  background: #ebaa28;
  border: 0;
  border-radius: 9px;
}

.card-hint {
  display: block;
  margin-top: 10px;
  font-size: 12px;
  color: var(--notice-color);
}

.transit-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 12px;
  color: var(--links-color);
}

.transit-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 12px;
  box-sizing: border-box;
  color: var(--text-color);
  text-decoration: none;
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 9px;
}

.transit-back:hover {
  background: var(--float-bg);
}

.transit-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 320px;
  font-size: 14px;
  color: var(--links-color);
}

.transit-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(var(--text-color-rgb), 0.2);
  border-top-color: var(--notice-color);
  border-radius: 50%;
  animation: transit-spin 0.9s linear infinite;
}

@keyframes transit-spin {
  to {
    transform: rotate(360deg);
  }
}

.transit-retry {
  padding: 7px 16px;
  font-size: 13px;
  color: inherit;
  cursor: pointer;
  background: var(--float-bg);
  border: 0;
  border-radius: 9px;
}

@media (max-width: 767px) {
  .transit-page {
    padding: 84px 14px 44px;
  }

  .transit-title {
    font-size: 24px;
  }

  .transit-canvas {
    height: 62vh;
  }

  .transit-card {
    top: auto;
    right: 10px;
    bottom: 10px;
    left: 10px;
    width: auto;
  }

  .transit-legend {
    margin-left: 0;
    width: 100%;
    /* 手机线路多时自动换行，避免挤成一排或横向滚动 */
    flex-wrap: wrap;
    overflow: visible;
    padding-bottom: 2px;
  }

  .legend-chip {
    flex: 0 0 auto;
  }
}
</style>

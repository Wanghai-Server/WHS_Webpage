<script setup>
/**
 * 轨交路线图编辑器（/map/transit/edit，permission ≥ 3）。
 *
 * - 桌面 ≥768px：左元素面板 / 中预览 / 右详情，未选中隐藏右栏，新建就地内联；
 * - 手机 <768px：顶部元素面板 + 预览，选中或新建时底部抽屉；
 * - 提交带 base_version：落后时自动合并，冲突 409 进冲突面板；
 * - 「强制并入」仅 can_force（permission ≥ 4）；
 * - 车站坐标可「从地图取点」：内嵌 BlueMap iframe，读相机 hash。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave } from 'vue-router'
import {
  ArrowDown, ArrowLeft, ArrowUp, History, MapPin, Plus, RotateCcw, Save, Search, Trash2, X,
} from 'lucide-vue-next'
import Top_navbar from '../../../components/top_navbar.vue'
import Page_footer from '../../../components/page_footer.vue'
import TransitDiagram from '../../../components/transit_diagram.vue'
import TransitPicker from '../../../components/transit_picker.vue'
import Markdown_editer from '../../../components/markdown_editer.vue'
import Status_dropdown from '../../../components/status_dropdown.vue'
import { useAuth } from '../../../composables/useAuth'
import { useDialogBox } from '../../../composables/useDialogBox'
import { useTips } from '../../../composables/useTips'
import { buildSchematic, lineName, stationName } from '../../../composables/transitLayout'
import { applyIncoming, mergeThreeWay } from '../../../composables/transitMerge'
import { PALETTE_FAMILIES, dyeLabel, familyLabel } from '../../../constants/mcPalette'

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const dialog = useDialogBox()
const { showTip } = useTips()

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const gate = ref('')
const payload = ref(null)
const doc = ref(null)
const baseVersion = ref('')
const savedSnapshot = ref('')
const baseDoc = ref(null)
const summary = ref('')
const selection = ref(null)
const activeTab = ref('lines')
const creating = ref('')
const draft = ref(null)
const conflict = ref(null)
const conflictBackup = ref(null)
const resolved = ref([])
const resolvedChoices = ref([])
const showHistory = ref(false)
const versions = ref([])
const historyLoading = ref(false)
const pickerOpen = ref(false)
const pickTarget = ref('station')
const addStationOpen = ref(false)
const addStationQuery = ref('')
const addStationPicked = ref([])
const isMobile = ref(false)
const colorFamily = ref(0)

const canForce = computed(() => !!payload.value?.can_force)
const typeOptions = computed(() => [
  { value: 'metro', label: t('transit.edit.typeMetro') },
  { value: 'rail', label: t('transit.edit.typeRail') },
  { value: 'bus', label: t('transit.edit.typeBus') },
])
const statusOptions = computed(() => [
  { value: 'open', label: t('transit.edit.statusOpen') },
  { value: 'building', label: t('transit.edit.statusBuilding') },
  { value: 'planned', label: t('transit.edit.statusPlanned') },
])
const lines = computed(() => doc.value?.lines || [])
const stations = computed(() => doc.value?.stations || [])
const schematic = computed(() => (doc.value ? buildSchematic(doc.value, { locale: locale.value }) : null))
const selectedLine = computed(() => (selection.value?.kind === 'line'
  ? lines.value.find((item) => item.id === selection.value.id) || null
  : null))
const selectedStation = computed(() => (selection.value?.kind === 'station'
  ? stations.value.find((item) => item.id === selection.value.id) || null
  : null))
const showPanel = computed(() => !!(selectedLine.value || selectedStation.value || creating.value))
const dirty = computed(() => (doc.value ? snapshot(doc.value) !== savedSnapshot.value : false))
const addableStations = computed(() => (selectedLine.value
  ? stations.value.filter((station) => !selectedLine.value.stations.includes(station.id))
  : []))
const filteredAddable = computed(() => addableStations.value.filter((station) => {
  const needle = addStationQuery.value.trim().toLowerCase()
  if (!needle) return true
  return `${station.id} ${stationName(station, locale.value)}`.toLowerCase().includes(needle)
}))
const activeColor = computed(() => selectedLine.value?.color || draft.value?.color || '#2f7fe0')
const allResolved = computed(() => (conflict.value?.conflicts || []).length === 0
  || resolved.value.every(Boolean))
const pickerInitial = computed(() => {
  if (pickTarget.value === 'new') {
    return { x: draft.value?.pos?.[0] || 0, z: draft.value?.pos?.[1] || 0, y: draft.value?.y || 80 }
  }
  return { x: selectedStation.value?.pos?.[0] || 0, z: selectedStation.value?.pos?.[1] || 0, y: selectedStation.value?.y || 80 }
})

function fitMedia() {
  isMobile.value = window.matchMedia('(max-width: 767px)').matches
}

// 手机编辑抽屉打开时隐藏左下角消息悬浮按钮，避免压住备注编辑区
function syncSheetClass() {
  document.body.classList.toggle('transit-sheet-open', isMobile.value && showPanel.value)
}

watch([isMobile, showPanel], syncSheetClass)

function authHeaders() {
  return authState.token ? { Authorization: `Bearer ${authState.token}` } : {}
}

/** 只保留落盘字段：去掉回填的 lines、来源为 default 的 y。 */
function toSendable(value) {
  const clone = JSON.parse(JSON.stringify(value))
  clone.stations = (clone.stations || []).map((station) => {
    const out = { id: station.id, name: station.name || {}, pos: [...(station.pos || [0, 0])] }
    if (station.tags?.length) out.tags = [...station.tags]
    if (station.note?.zh || station.note?.en) out.note = station.note
    if (station.y_source && station.y_source !== 'default' && station.y != null) {
      out.y = station.y
      out.y_source = station.y_source
    }
    return out
  })
  clone.lines = (clone.lines || []).map((line) => ({
    id: line.id,
    name: line.name || {},
    color: line.color,
    type: line.type || 'metro',
    status: line.status || 'open',
    stations: [...(line.stations || [])],
    ...(line.note?.zh || line.note?.en ? { note: line.note } : {}),
  }))
  if (!(clone.note?.zh || clone.note?.en)) delete clone.note
  return { ...(clone.note ? { note: clone.note } : {}), lines: clone.lines, stations: clone.stations }
}

function snapshot(value) {
  return JSON.stringify(toSendable(value))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/map/transit', { headers: authHeaders() })
    const body = await res.json().catch(() => ({}))
    payload.value = body
    if (!body.available) {
      error.value = body.error || t('transit.unavailable')
      return
    }
    if (!body.can_edit) {
      gate.value = authState.user ? 'permission' : 'login'
      return
    }
    doc.value = normalizeDoc(toSendable(body.data))
    baseDoc.value = toSendable(body.data)
    baseVersion.value = body.version
    savedSnapshot.value = snapshot(doc.value)
  } catch {
    error.value = t('transit.loadFailed')
  } finally {
    loading.value = false
  }
}

function normalizeDoc(value) {
  const clone = JSON.parse(JSON.stringify(value))
  for (const key of ['lines', 'stations']) {
    clone[key] = (clone[key] || []).map((item) => ({
      ...item,
      note: { zh: item.note?.zh || '', en: item.note?.en || '' },
    }))
  }
  return clone
}

function onDiagramSelect({ kind, id }) {
  select(kind, id)
}

function select(kind, id) {
  selection.value = { kind, id }
  creating.value = ''
  const target = kind === 'line'
    ? lines.value.find((item) => item.id === id)
    : stations.value.find((item) => item.id === id)
  if (target && !target.note) target.note = { zh: '', en: '' }
}

function startCreate(kind) {
  creating.value = kind
  selection.value = null
  colorFamily.value = 0
  if (kind === 'line') {
    draft.value = { id: `l${lines.value.length + 1}`, name: { zh: '', en: '' }, color: '#2f7fe0', type: 'metro', status: 'open', note: { zh: '', en: '' } }
  } else {
    draft.value = {
      id: `s_${Math.random().toString(36).slice(2, 6)}`,
      name: { zh: '', en: '' },
      pos: [0, 0],
      y: null,
      y_source: null,
      tags: '',
      note: { zh: '', en: '' },
    }
  }
}

function cancelCreate() {
  creating.value = ''
  draft.value = null
}

function confirmCreate() {
  if (!draft.value) return
  if (!draft.value.name.zh && !draft.value.name.en) {
    showTip('warning', t('transit.edit.nameRequired'))
    return
  }
  if (creating.value === 'line') {
    if (doc.value.lines.some((line) => line.id === draft.value.id)) {
      showTip('error', t('transit.edit.idTaken'))
      return
    }
    doc.value.lines.push({ ...draft.value, stations: [] })
    selection.value = { kind: 'line', id: draft.value.id }
  } else {
    if (doc.value.stations.some((station) => station.id === draft.value.id)) {
      showTip('error', t('transit.edit.idTaken'))
      return
    }
    const station = {
      id: draft.value.id,
      name: { ...draft.value.name },
      pos: [...draft.value.pos],
      note: { zh: draft.value.note?.zh || '', en: draft.value.note?.en || '' },
    }
    const tags = String(draft.value.tags || '').split(',').map((item) => item.trim()).filter(Boolean)
    if (tags.length) station.tags = tags
    if (draft.value.y != null) {
      station.y = Number(draft.value.y)
      station.y_source = draft.value.y_source || 'explicit'
    }
    doc.value.stations.push(station)
    selection.value = { kind: 'station', id: station.id }
  }
  creating.value = ''
  draft.value = null
}

async function deleteLine(line) {
  const ok = await dialog.confirm({
    title: t('transit.edit.deleteLineTitle'),
    message: t('transit.edit.deleteLineMessage', { name: lineName(line, locale.value) }),
    danger: true,
    confirmText: t('transit.edit.delete'),
  })
  if (!ok) return
  doc.value.lines = doc.value.lines.filter((item) => item.id !== line.id)
  selection.value = null
}

async function deleteStation(station) {
  if (lines.value.some((line) => line.stations.includes(station.id))) {
    showTip('warning', t('transit.edit.stationInUse'))
    return
  }
  const ok = await dialog.confirm({
    title: t('transit.edit.deleteStationTitle'),
    message: t('transit.edit.deleteStationMessage', { name: stationName(station, locale.value) }),
    danger: true,
    confirmText: t('transit.edit.delete'),
  })
  if (!ok) return
  doc.value.stations = doc.value.stations.filter((item) => item.id !== station.id)
  selection.value = null
}

function moveLine(line, delta) {
  const list = doc.value.lines
  const index = list.findIndex((item) => item.id === line.id)
  const next = index + delta
  if (index < 0 || next < 0 || next >= list.length) return
  const [item] = list.splice(index, 1)
  list.splice(next, 0, item)
}

function moveStationInLine(line, index, delta) {
  const next = index + delta
  if (next < 0 || next >= line.stations.length) return
  const [id] = line.stations.splice(index, 1)
  line.stations.splice(next, 0, id)
}

function openAddStation() {
  addStationQuery.value = ''
  addStationPicked.value = []
  addStationOpen.value = true
}

function toggleAddStation(id) {
  const index = addStationPicked.value.indexOf(id)
  if (index >= 0) addStationPicked.value.splice(index, 1)
  else addStationPicked.value.push(id)
}

function confirmAddStations() {
  const line = selectedLine.value
  if (!line || !addStationPicked.value.length) return
  for (const id of addStationPicked.value) {
    if (!line.stations.includes(id)) line.stations.push(id)
  }
  addStationOpen.value = false
  addStationPicked.value = []
}

function removeStationFromLine(line, id) {
  line.stations = line.stations.filter((item) => item !== id)
}

function setColor(hex) {
  if (selectedLine.value) selectedLine.value.color = hex
  else if (draft.value) draft.value.color = hex
}

function setY(station, raw) {
  const value = raw === '' || raw == null ? null : Number(raw)
  if (value == null || !Number.isFinite(value)) {
    delete station.y
    delete station.y_source
    return
  }
  station.y = Math.round(value)
  station.y_source = 'explicit'
}

function clearY(station) {
  delete station.y
  delete station.y_source
}

function tagsValue(station) {
  return (station.tags || []).join(', ')
}

function setTags(station, value) {
  const tags = String(value || '').split(',').map((item) => item.trim()).filter(Boolean)
  if (tags.length) station.tags = tags
  else delete station.tags
}

function openPicker(target) {
  pickTarget.value = target
  pickerOpen.value = true
}

function onPicked(coords) {
  pickerOpen.value = false
  if (pickTarget.value === 'new' && draft.value) {
    draft.value.pos = [coords.x, coords.z]
    draft.value.y = coords.y
    draft.value.y_source = 'picked'
    return
  }
  if (selectedStation.value) {
    selectedStation.value.pos = [coords.x, coords.z]
    selectedStation.value.y = coords.y
    selectedStation.value.y_source = 'picked'
  }
}

function validateLocal() {
  for (const line of doc.value.lines) {
    if (!line.name?.zh && !line.name?.en) return t('transit.edit.nameRequired')
    if (!/^#[0-9a-fA-F]{6}$/.test(line.color || '')) return t('transit.edit.errColor')
    if ((line.stations || []).length < 2) return t('transit.edit.errStations')
  }
  for (const station of doc.value.stations) {
    if (!Array.isArray(station.pos) || station.pos.length !== 2 || !station.pos.every(Number.isInteger)) {
      return t('transit.edit.errPos')
    }
  }
  return ''
}

async function save(options = {}) {
  if (!doc.value || saving.value) return
  if (!options.skipValidate) {
    const message = validateLocal()
    if (message) {
      showTip('warning', message)
      return
    }
  }
  saving.value = true
  error.value = ''
  try {
    const res = await fetch('/api/map/transit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        base_version: options.base || baseVersion.value,
        summary: summary.value,
        data: options.data || toSendable(doc.value),
        force: options.force === true,
      }),
    })
    const body = await res.json().catch(() => ({}))
    if (res.status === 409) {
      const detail = body.detail || {}
      conflictBackup.value = JSON.parse(JSON.stringify(doc.value))
      conflict.value = {
        ...detail,
        current: detail.current ? normalizeDoc(toSendable(detail.current)) : null,
      }
      resolved.value = (conflict.value.conflicts || []).map(() => false)
      resolvedChoices.value = []
      return
    }
    if (!res.ok) {
      error.value = body.message?.[locale.value] || body.detail || t('transit.edit.saveFailed')
      return
    }
    await reload(body.version)
    conflict.value = null
    conflictBackup.value = null
    showTip('info', t('transit.edit.saved'))
  } catch {
    error.value = t('transit.edit.saveFailed')
  } finally {
    saving.value = false
  }
}

async function reload(version) {
  const res = await fetch('/api/map/transit', { headers: authHeaders() })
  const body = await res.json().catch(() => ({}))
  if (!body.available) return
  payload.value = body
  doc.value = normalizeDoc(toSendable(body.data))
  baseDoc.value = toSendable(body.data)
  baseVersion.value = version || body.version
  savedSnapshot.value = snapshot(doc.value)
  summary.value = ''
}

function applyTheirValue(item) {
  if (item.path.startsWith('note.')) {
    if (!doc.value.note) doc.value.note = { zh: '', en: '' }
    doc.value.note[item.path.slice(5)] = item.current == null ? '' : item.current
    return
  }
  const match = /^(lines|stations)\[([^\]]+)\](?:\.(.+))?$/.exec(item.path)
  if (!match) return
  const [, kind, id, rest] = match
  if (rest === undefined) {
    if (item.current == null) {
      if (kind === 'lines') doc.value.lines = doc.value.lines.filter((entry) => entry.id !== id)
      else doc.value.stations = doc.value.stations.filter((entry) => entry.id !== id)
    }
    return
  }
  const list = kind === 'lines' ? doc.value.lines : doc.value.stations
  const target = list.find((entry) => entry.id === id)
  if (!target) {
    if (item.current && typeof item.current === 'object') list.push(JSON.parse(JSON.stringify(item.current)))
    return
  }
  const parts = rest.split('.')
  let node = target
  for (const part of parts.slice(0, -1)) {
    if (!node[part] || typeof node[part] !== 'object') node[part] = {}
    node = node[part]
  }
  node[parts[parts.length - 1]] = item.current == null ? '' : item.current
}

function resolveConflict(index, keepMine) {
  resolvedChoices.value[index] = keepMine ? 'mine' : 'theirs'
  if (!keepMine) applyTheirValue(conflict.value.conflicts[index])
  resolved.value[index] = true
}

async function submitResolved() {
  if (!conflict.value) return
  const current = conflict.value.current ? toSendable(conflict.value.current) : null
  if (!current) {
    await save({ base: conflict.value.current_version || baseVersion.value })
    return
  }
  const local = toSendable(doc.value)
  const base = baseDoc.value || local
  const { data } = mergeThreeWay(base, current, local)
  conflict.value.conflicts.forEach((item, index) => {
    if (resolvedChoices.value[index] === 'mine') applyIncoming(data, item.path, item.incoming)
  })
  await save({ data, base: conflict.value.current_version, skipValidate: true })
}

function closeConflict() {
  // 取消冲突面板时，把已经点过「用线上」而应用的改动回滚掉
  if (conflictBackup.value && resolved.value.some(Boolean)) {
    doc.value = JSON.parse(JSON.stringify(conflictBackup.value))
  }
  conflict.value = null
  conflictBackup.value = null
  resolved.value = []
  resolvedChoices.value = []
}

async function forceMerge() {
  const ok = await dialog.confirm({
    title: t('transit.edit.forceTitle'),
    message: t('transit.edit.forceMessage'),
    danger: true,
    confirmText: t('transit.edit.forceConfirm'),
  })
  if (!ok) return
  await save({ base: conflict.value?.current_version || baseVersion.value, force: true })
}

async function openHistory() {
  showHistory.value = true
  historyLoading.value = true
  try {
    const res = await fetch('/api/map/transit/versions')
    const body = await res.json().catch(() => ({}))
    versions.value = body.versions || []
  } finally {
    historyLoading.value = false
  }
}

async function resetDoc() {
  if (!dirty.value) return
  const ok = await dialog.confirm({
    title: t('transit.edit.resetTitle'),
    message: t('transit.edit.resetMessage'),
    danger: true,
    confirmText: t('transit.edit.reset'),
  })
  if (!ok) return
  const res = await fetch('/api/map/transit', { headers: authHeaders() })
  const body = await res.json().catch(() => ({}))
  if (!body.available) return
  payload.value = body
  doc.value = normalizeDoc(toSendable(body.data))
  baseDoc.value = toSendable(body.data)
  baseVersion.value = body.version
  savedSnapshot.value = snapshot(doc.value)
  summary.value = ''
}

async function rollback(version) {
  if (dirty.value && !window.confirm(t('transit.edit.rollbackDirty'))) return
  const ok = await dialog.confirm({
    title: t('transit.edit.rollbackTitle'),
    message: t('transit.edit.rollbackMessage', { id: version.id }),
    confirmText: t('transit.edit.rollback'),
  })
  if (!ok) return
  saving.value = true
  try {
    const res = await fetch('/api/map/transit/rollback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ version_id: version.id }),
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      showTip('error', body.detail || t('transit.edit.saveFailed'))
      return
    }
    await reload(body.version)
    showHistory.value = false
    showTip('info', t('transit.edit.rolledBack'))
  } finally {
    saving.value = false
  }
}

function beforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => {
  if (!dirty.value) return true
  return window.confirm(t('transit.edit.unsaved'))
})

onMounted(() => {
  fitMedia()
  window.addEventListener('resize', fitMedia)
  window.addEventListener('beforeunload', beforeUnload)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', fitMedia)
  window.removeEventListener('beforeunload', beforeUnload)
  document.body.classList.remove('transit-sheet-open')
})
</script>

<template>
  <Top_navbar />

  <main class="edit-page">
    <header class="edit-head">
      <div class="head-left">
        <RouterLink to="/map/transit" class="btn-ghost back-btn">
          <ArrowLeft :size="14" /> {{ t('transit.edit.back') }}
        </RouterLink>
        <h1>{{ t('transit.edit.title') }}</h1>
        <span v-if="baseVersion" class="version-badge">v{{ baseVersion }}</span>
      </div>
      <div class="head-actions">
        <input
          v-model="summary"
          class="summary-input"
          type="text"
          :placeholder="t('transit.edit.summaryPlaceholder')"
          :aria-label="t('transit.edit.summary')"
        />
        <button type="button" class="btn-ghost" @click="openHistory">
          <History :size="15" /> {{ t('transit.edit.history') }}
        </button>
        <button type="button" class="btn-ghost" :disabled="!dirty" @click="resetDoc">
          <RotateCcw :size="15" /> {{ t('transit.edit.reset') }}
        </button>
        <button type="button" class="btn-primary" :disabled="saving || !dirty" @click="save()">
          <Save :size="15" /> {{ saving ? t('transit.edit.saving') : t('transit.edit.save') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="edit-error">{{ error }}</p>
    <div v-if="loading" class="edit-state">{{ t('transit.loading') }}</div>

    <div v-else-if="gate" class="edit-gate">
      <h2>{{ t('transit.edit.needPermission') }}</h2>
      <RouterLink v-if="gate === 'login'" to="/login" class="btn-primary">{{ t('transit.edit.goLogin') }}</RouterLink>
      <RouterLink v-else to="/joinus" class="btn-primary">{{ t('transit.edit.goExam') }}</RouterLink>
    </div>

    <div v-else-if="doc" class="edit-grid" :class="{ 'no-detail': !showPanel }">
      <aside class="panel panel-list">
        <div class="panel-tabs">
          <button type="button" :class="{ active: activeTab === 'lines' }" @click="activeTab = 'lines'">
            {{ t('transit.edit.lines') }} <span>{{ lines.length }}</span>
          </button>
          <button type="button" :class="{ active: activeTab === 'stations' }" @click="activeTab = 'stations'">
            {{ t('transit.edit.stations') }} <span>{{ stations.length }}</span>
          </button>
        </div>

        <div v-if="activeTab === 'lines'" class="list-body">
          <button type="button" class="add-btn" @click="startCreate('line')">
            <Plus :size="14" /> {{ t('transit.edit.newLine') }}
          </button>
          <ul class="element-list">
            <li
              v-for="line in lines"
              :key="line.id"
              :class="{ active: selection?.kind === 'line' && selection.id === line.id }"
              @click="select('line', line.id)"
            >
              <span class="line-swatch" :style="{ background: line.color }"></span>
              <span class="element-name">{{ lineName(line, locale) }}</span>
              <span class="element-meta">{{ line.status }}</span>
            </li>
          </ul>
        </div>

        <div v-else class="list-body">
          <button type="button" class="add-btn" @click="startCreate('station')">
            <Plus :size="14" /> {{ t('transit.edit.newStation') }}
          </button>
          <ul class="element-list">
            <li
              v-for="station in stations"
              :key="station.id"
              :class="{ active: selection?.kind === 'station' && selection.id === station.id }"
              @click="select('station', station.id)"
            >
              <span class="station-dot-mini"></span>
              <span class="element-name">{{ stationName(station, locale) }}</span>
              <span class="element-meta">{{ station.pos[0] }}, {{ station.pos[1] }}</span>
            </li>
          </ul>
        </div>
      </aside>

      <section class="panel panel-preview">
        <TransitDiagram
          :schematic="schematic"
          :selected-id="selection?.id || ''"
          @select="onDiagramSelect"
        />
        <p class="preview-hint">{{ t('transit.edit.previewHint') }}</p>
      </section>

      <Transition name="sheet">
      <aside v-if="showPanel" class="panel panel-detail" :class="{ 'is-sheet': isMobile }">
        <header class="detail-head">
          <h2>{{ selectedLine ? t('transit.edit.line') : selectedStation ? t('transit.edit.station') : t('transit.edit.create') }}</h2>
          <button type="button" class="icon-btn" @click="selection = null; cancelCreate()"><X :size="16" /></button>
        </header>

        <div v-if="creating" class="detail-body">
          <label class="field"><span>{{ t('transit.edit.id') }}</span><input v-model="draft.id" class="input" /></label>
          <label class="field"><span>{{ t('transit.edit.nameZh') }}</span><input v-model="draft.name.zh" class="input" /></label>
          <label class="field"><span>{{ t('transit.edit.nameEn') }}</span><input v-model="draft.name.en" class="input" /></label>
          <template v-if="creating === 'line'">
            <div class="field-row">
              <label class="field"><span>{{ t('transit.edit.type') }}</span>
                <Status_dropdown v-model="draft.type" :options="typeOptions" variant="select" />
              </label>
              <label class="field"><span>{{ t('transit.edit.status') }}</span>
                <Status_dropdown v-model="draft.status" :options="statusOptions" variant="select" />
              </label>
            </div>
            <div class="field"><span>{{ t('transit.edit.color') }}</span>
              <div class="palette">
                <div class="palette-tabs">
                  <button
                    v-for="(family, index) in PALETTE_FAMILIES"
                    :key="family.key"
                    type="button"
                    class="palette-tab"
                    :class="{ active: colorFamily === index }"
                    @click="colorFamily = index"
                  >{{ familyLabel(family, locale) }}</button>
                </div>
                <div class="palette-colors">
                  <button
                    v-for="(color, index) in PALETTE_FAMILIES[colorFamily].colors"
                    :key="color"
                    type="button"
                    class="swatch"
                    :class="{ active: activeColor.toLowerCase() === color.toLowerCase() }"
                    :style="{ background: color }"
                    :title="dyeLabel(index, locale)"
                    @click="setColor(color)"
                  ></button>
                </div>
                <input v-model="draft.color" class="input input-color" :placeholder="t('transit.edit.customColor')" />
              </div>
            </div>
            <div class="field note-field">
              <span>{{ t('transit.edit.note') }}</span>
              <Markdown_editer v-model="draft.note" multilingual :min-height="120" :placeholder="t('transit.edit.notePlaceholder')" />
            </div>
          </template>
          <template v-else>
            <div class="field-row">
              <label class="field"><span>{{ t('transit.edit.posX') }}</span><input v-model.number="draft.pos[0]" class="input" type="number" /></label>
              <label class="field"><span>{{ t('transit.edit.posZ') }}</span><input v-model.number="draft.pos[1]" class="input" type="number" /></label>
            </div>
            <button type="button" class="btn-ghost full" @click="openPicker('new')"><MapPin :size="14" /> {{ t('transit.edit.pick') }}</button>
            <div class="field-row">
              <label class="field"><span>{{ t('transit.edit.y') }}</span>
                <input v-model.number="draft.y" class="input" type="number" :placeholder="t('transit.edit.yAuto')" />
              </label>
              <button type="button" class="btn-ghost self-end" @click="draft.y = null">{{ t('transit.edit.yClear') }}</button>
            </div>
            <label class="field"><span>{{ t('transit.edit.tags') }}</span><input v-model="draft.tags" class="input" :placeholder="t('transit.edit.tagHint')" /></label>
            <div class="field note-field">
              <span>{{ t('transit.edit.note') }}</span>
              <Markdown_editer v-model="draft.note" multilingual :min-height="120" :placeholder="t('transit.edit.notePlaceholder')" />
            </div>
          </template>
          <div class="detail-actions">
            <button type="button" class="btn-ghost" @click="cancelCreate">{{ t('transit.edit.cancel') }}</button>
            <button type="button" class="btn-primary" @click="confirmCreate">{{ t('transit.edit.create') }}</button>
          </div>
        </div>

        <div v-else-if="selectedLine" class="detail-body">
          <label class="field"><span>{{ t('transit.edit.nameZh') }}</span><input v-model="selectedLine.name.zh" class="input" /></label>
          <label class="field"><span>{{ t('transit.edit.nameEn') }}</span><input v-model="selectedLine.name.en" class="input" /></label>
          <div class="field-row">
            <label class="field"><span>{{ t('transit.edit.type') }}</span>
              <Status_dropdown v-model="selectedLine.type" :options="typeOptions" variant="select" />
            </label>
            <label class="field"><span>{{ t('transit.edit.status') }}</span>
              <Status_dropdown v-model="selectedLine.status" :options="statusOptions" variant="select" />
            </label>
          </div>
          <div class="field"><span>{{ t('transit.edit.color') }}</span>
            <div class="palette">
              <div class="palette-tabs">
                <button
                  v-for="(family, index) in PALETTE_FAMILIES"
                  :key="family.key"
                  type="button"
                  class="palette-tab"
                  :class="{ active: colorFamily === index }"
                  @click="colorFamily = index"
                >{{ familyLabel(family, locale) }}</button>
              </div>
              <div class="palette-colors">
                <button
                  v-for="(color, index) in PALETTE_FAMILIES[colorFamily].colors"
                  :key="color"
                  type="button"
                  class="swatch"
                  :class="{ active: activeColor.toLowerCase() === color.toLowerCase() }"
                  :style="{ background: color }"
                  :title="dyeLabel(index, locale)"
                  @click="setColor(color)"
                ></button>
              </div>
              <input v-model="selectedLine.color" class="input input-color" :placeholder="t('transit.edit.customColor')" />
            </div>
          </div>
          <div class="field"><span>{{ t('transit.edit.stationsOfLine') }}</span>
            <ol class="station-seq">
              <li v-for="(id, index) in selectedLine.stations" :key="id">
                <span class="seq-index">{{ index + 1 }}</span>
                <span class="seq-name">{{ stationName(stations.find((item) => item.id === id) || {}, locale) || id }}</span>
                <button type="button" class="icon-btn" :disabled="index === 0" @click="moveStationInLine(selectedLine, index, -1)"><ArrowUp :size="13" /></button>
                <button type="button" class="icon-btn" :disabled="index === selectedLine.stations.length - 1" @click="moveStationInLine(selectedLine, index, 1)"><ArrowDown :size="13" /></button>
                <button type="button" class="icon-btn danger" @click="removeStationFromLine(selectedLine, id)"><Trash2 :size="13" /></button>
              </li>
            </ol>
            <button type="button" class="btn-ghost full" :disabled="!addableStations.length" @click="openAddStation">
              <Plus :size="14" /> {{ addableStations.length ? t('transit.edit.addStationBtn') : t('transit.edit.noStationLeft') }}
            </button>
          </div>
          <div class="field note-field">
            <span>{{ t('transit.edit.note') }}</span>
            <Markdown_editer v-model="selectedLine.note" multilingual :min-height="150" :placeholder="t('transit.edit.notePlaceholder')" />
          </div>
          <div class="detail-actions">
            <button type="button" class="icon-btn" :disabled="lines[0]?.id === selectedLine.id" @click="moveLine(selectedLine, -1)"><ArrowUp :size="14" /></button>
            <button type="button" class="icon-btn" :disabled="lines[lines.length - 1]?.id === selectedLine.id" @click="moveLine(selectedLine, 1)"><ArrowDown :size="14" /></button>
            <button type="button" class="btn-danger" @click="deleteLine(selectedLine)"><Trash2 :size="14" /> {{ t('transit.edit.delete') }}</button>
          </div>
        </div>

        <div v-else-if="selectedStation" class="detail-body">
          <label class="field"><span>{{ t('transit.edit.nameZh') }}</span><input v-model="selectedStation.name.zh" class="input" /></label>
          <label class="field"><span>{{ t('transit.edit.nameEn') }}</span><input v-model="selectedStation.name.en" class="input" /></label>
          <div class="field-row">
            <label class="field"><span>{{ t('transit.edit.posX') }}</span><input v-model.number="selectedStation.pos[0]" class="input" type="number" /></label>
            <label class="field"><span>{{ t('transit.edit.posZ') }}</span><input v-model.number="selectedStation.pos[1]" class="input" type="number" /></label>
          </div>
          <button type="button" class="btn-ghost full" @click="openPicker('station')"><MapPin :size="14" /> {{ t('transit.edit.pick') }}</button>
          <div class="field-row">
            <label class="field"><span>{{ t('transit.edit.y') }}</span>
              <input :value="selectedStation.y ?? ''" class="input" type="number" :placeholder="t('transit.edit.yAuto')" @input="setY(selectedStation, $event.target.value)" />
            </label>
            <button type="button" class="btn-ghost self-end" @click="clearY(selectedStation)">{{ t('transit.edit.yClear') }}</button>
          </div>
          <p class="hint-text">
            {{ selectedStation.y_source === 'picked' ? t('transit.edit.yPicked') : selectedStation.y_source === 'explicit' ? t('transit.edit.yManual') : t('transit.edit.yAutoHint') }}
          </p>
          <label class="field"><span>{{ t('transit.edit.tags') }}</span>
            <input :value="tagsValue(selectedStation)" class="input" @change="setTags(selectedStation, $event.target.value)" />
          </label>
          <div class="field note-field">
            <span>{{ t('transit.edit.note') }}</span>
            <Markdown_editer v-model="selectedStation.note" multilingual :min-height="150" :placeholder="t('transit.edit.notePlaceholder')" />
          </div>
          <div class="detail-actions">
            <button type="button" class="btn-danger" @click="deleteStation(selectedStation)"><Trash2 :size="14" /> {{ t('transit.edit.delete') }}</button>
          </div>
        </div>
      </aside>
      </Transition>
    </div>

    <Transition name="dialog-fade">
    <div v-if="showHistory" class="modal-overlay is-glass" @click.self="showHistory = false">
      <section class="modal dialog">
        <header class="modal-head">
          <h2>{{ t('transit.edit.historyTitle') }}</h2>
          <button type="button" class="icon-btn" @click="showHistory = false"><X :size="16" /></button>
        </header>
        <div v-if="historyLoading" class="modal-state">{{ t('transit.loading') }}</div>
        <ul v-else class="version-list">
          <li v-for="(version, index) in versions" :key="version.id">
            <div class="version-main">
              <span class="version-id">{{ version.id }}</span>
              <span v-if="index === 0" class="version-current">{{ t('transit.edit.currentVersion') }}</span>
              <span class="version-summary">{{ version.summary }}</span>
            </div>
            <div class="version-meta">
              <span>{{ (version.created_at || '').slice(0, 19).replace('T', ' ') }}</span>
              <span>{{ version.author?.name || '—' }}</span>
              <span>{{ version.stats?.lines }} / {{ version.stats?.stations }}</span>
            </div>
            <button type="button" class="btn-ghost" :disabled="saving" @click="rollback(version)">
              <RotateCcw :size="13" /> {{ t('transit.edit.rollback') }}
            </button>
          </li>
        </ul>
      </section>
    </div>
    </Transition>

    <Transition name="dialog-fade">
    <div v-if="conflict" class="modal-overlay is-glass">
      <section class="modal dialog">
        <header class="modal-head">
          <h2>{{ t('transit.edit.conflictTitle') }}</h2>
          <button type="button" class="icon-btn" :aria-label="t('transit.edit.cancel')" @click="closeConflict"><X :size="16" /></button>
        </header>
        <p class="hint-text">{{ t('transit.edit.conflictHint', { base: conflict.base_version, current: conflict.current_version }) }}</p>
        <p v-if="!conflict.conflicts.length" class="hint-text">{{ t('transit.edit.conflictEmpty') }}</p>
        <ul v-else class="conflict-list">
          <li v-for="(item, index) in conflict.conflicts" :key="item.path" :class="{ resolved: resolved[index] }">
            <code>{{ item.path }}</code>
            <div class="conflict-values">
              <span>{{ t('transit.edit.conflictTheirs') }}: {{ JSON.stringify(item.current) }}</span>
              <span>{{ t('transit.edit.conflictMine') }}: {{ JSON.stringify(item.incoming) }}</span>
            </div>
            <div class="conflict-actions">
              <button type="button" class="btn-ghost" :disabled="resolved[index]" @click="resolveConflict(index, true)">{{ t('transit.edit.conflictKeepMine') }}</button>
              <button type="button" class="btn-ghost" :disabled="resolved[index]" @click="resolveConflict(index, false)">{{ t('transit.edit.conflictKeepTheirs') }}</button>
            </div>
          </li>
        </ul>
        <footer class="modal-actions">
          <button type="button" class="btn-ghost" @click="closeConflict">{{ t('transit.edit.cancel') }}</button>
          <button v-if="canForce" type="button" class="btn-danger" @click="forceMerge">{{ t('transit.edit.forceMerge') }}</button>
          <button type="button" class="btn-primary" :disabled="!allResolved || saving" @click="submitResolved">{{ t('transit.edit.conflictResubmit') }}</button>
        </footer>
      </section>
    </div>
    </Transition>

    <Transition name="dialog-fade">
    <div v-if="addStationOpen" class="modal-overlay is-glass" @click.self="addStationOpen = false">
      <section class="modal dialog">
        <header class="modal-head">
          <h2>{{ t('transit.edit.addStationTitle') }}</h2>
          <button type="button" class="icon-btn" :aria-label="t('transit.edit.cancel')" @click="addStationOpen = false"><X :size="16" /></button>
        </header>
        <p class="hint-text">{{ t('transit.edit.addStationHint') }}</p>
        <label class="search-field">
          <Search :size="14" aria-hidden="true" />
          <input v-model="addStationQuery" :placeholder="t('transit.edit.addStationSearch')" />
        </label>
        <ul v-if="filteredAddable.length" class="add-station-list">
          <li v-for="station in filteredAddable" :key="station.id">
            <label>
              <input
                type="checkbox"
                :checked="addStationPicked.includes(station.id)"
                @change="toggleAddStation(station.id)"
              />
              <span>{{ stationName(station, locale) }}</span>
              <code>{{ station.id }}</code>
            </label>
          </li>
        </ul>
        <p v-else class="hint-text">{{ t('transit.edit.noStationLeft') }}</p>
        <footer class="modal-actions">
          <button type="button" class="btn-ghost" @click="addStationOpen = false">{{ t('transit.edit.cancel') }}</button>
          <button type="button" class="btn-primary" :disabled="!addStationPicked.length" @click="confirmAddStations">
            {{ t('transit.edit.addStationConfirm', { count: addStationPicked.length }) }}
          </button>
        </footer>
      </section>
    </div>
    </Transition>

    <TransitPicker
      :open="pickerOpen"
      :initial="pickerInitial"
      @close="pickerOpen = false"
      @pick="onPicked"
    />
  </main>

  <Page_footer />
</template>

<style scoped>
.edit-page {
  max-width: 1440px;
  margin: 0 auto;
  /* 顶部留出固定导航胶囊的高度 */
  padding: 84px 20px 48px;
}

.edit-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.head-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.back-link {
  font-size: 13px;
  color: var(--links-color);
  text-decoration: none;
}

.back-btn {
  height: 34px;
  padding: 0 12px;
  font-size: 12px;
  text-decoration: none;
}

.head-actions .btn-ghost,
.head-actions .btn-primary {
  height: 34px;
  padding: 0 12px;
}

.summary-input {
  height: 34px;
  box-sizing: border-box;
}

.edit-head h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
}

.version-badge {
  padding: 2px 8px;
  font-size: 12px;
  font-family: ui-monospace, Menlo, monospace;
  background: var(--float-bg);
  border-radius: 999px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.summary-input {
  min-width: 210px;
  padding: 8px 11px;
  font-size: 13px;
  color: var(--text-color);
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.14);
  border-radius: 9px;
  outline: none;
}

.edit-error {
  margin: 0 0 12px;
  padding: 9px 12px;
  font-size: 13px;
  color: #b91c1c;
  background: rgba(185, 28, 28, 0.08);
  border-radius: 9px;
}

.edit-state,
.edit-gate {
  padding: 40px 0;
  text-align: center;
  color: var(--links-color);
}

.edit-grid {
  display: grid;
  grid-template-columns: minmax(230px, 300px) 1fr minmax(280px, 360px);
  gap: 14px;
  /* 三块面板等高：网格行高固定，子元素拉伸填满 */
  align-items: stretch;
  height: min(74vh, 760px);
}

.edit-grid.no-detail {
  grid-template-columns: minmax(230px, 300px) 1fr;
}

.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
  /* 与全站导航/弹窗同款毛玻璃 */
  background: rgba(var(--card-color-rgb), 0.72);
  -webkit-backdrop-filter: blur(18px) saturate(1.15);
  backdrop-filter: blur(18px) saturate(1.15);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 14px;
}

.panel-list {
  display: flex;
  flex-direction: column;
}

.panel-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  min-height: 420px;
}

.panel-preview :deep(.transit-diagram) {
  flex: 1;
}

.preview-hint {
  margin: 0;
  font-size: 11px;
  color: var(--links-color);
  text-align: center;
}

.panel-tabs {
  display: flex;
  border-bottom: 1px solid rgba(var(--text-color-rgb), 0.1);
}

.panel-tabs button {
  flex: 1;
  padding: 10px 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--links-color);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
}

.panel-tabs button.active {
  color: var(--text-color);
  border-bottom-color: var(--notice-color);
}

.panel-tabs span {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.7;
}

.list-body {
  flex: 1;
  min-height: 0;
  padding: 10px;
  overflow-y: auto;
}

.add-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  width: 100%;
  padding: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--text-color);
  cursor: pointer;
  background: var(--float-bg);
  border: 0;
  border-radius: 9px;
}

.inline-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 9px;
  margin-bottom: 8px;
  background: var(--float-bg);
  border-radius: 10px;
}

.inline-row {
  display: flex;
  gap: 6px;
}

.inline-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.element-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.element-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  font-size: 13px;
  cursor: pointer;
  border-radius: 9px;
}

.element-list li:hover {
  background: var(--float-bg);
}

.element-list li.active {
  background: var(--float-bg);
  box-shadow: inset 2px 0 0 var(--notice-color);
}

.element-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.element-meta {
  font-size: 11px;
  color: var(--links-color);
}

.line-swatch {
  width: 14px;
  height: 6px;
  border-radius: 3px;
}

.station-dot-mini {
  width: 9px;
  height: 9px;
  background: var(--text-color);
  border-radius: 50%;
}

.panel-detail {
  display: flex;
  flex-direction: column;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(var(--text-color-rgb), 0.1);
}

.detail-head h2 {
  margin: 0;
  font-size: 14px;
}

.detail-body {
  flex: 1;
  padding: 10px 12px 14px;
  overflow-y: auto;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 9px;
  font-size: 12px;
  color: var(--links-color);
}

.field-row {
  display: flex;
  gap: 8px;
}

.field-row .field {
  flex: 1;
}

.input {
  width: 100%;
  padding: 7px 9px;
  font-size: 13px;
  color: var(--text-color);
  background: var(--bg-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.14);
  border-radius: 8px;
  outline: none;
  box-sizing: border-box;
}

.input-color {
  font-family: ui-monospace, Menlo, monospace;
}

.palette {
  padding: 8px;
  background: var(--bg-color);
  border-radius: 10px;
}

.palette-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}

.palette-tab {
  padding: 3px 8px;
  font-size: 11px;
  color: var(--links-color);
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 999px;
}

.palette-tab.active {
  color: var(--text-color);
  border-color: rgba(var(--text-color-rgb), 0.2);
}

.palette-colors {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 5px;
  margin-bottom: 6px;
}

.swatch {
  width: 100%;
  aspect-ratio: 1;
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 5px;
}

.swatch.active {
  border-color: var(--text-color);
}

.station-seq {
  margin: 0 0 6px;
  padding: 0;
  list-style: none;
}

.station-seq li {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 0;
  font-size: 12px;
}

.seq-index {
  width: 18px;
  font-family: ui-monospace, Menlo, monospace;
  color: var(--links-color);
}

.seq-name {
  flex: 1;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  color: inherit;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.icon-btn:hover {
  background: var(--float-bg);
}

.icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.icon-btn.danger:hover {
  color: #b91c1c;
  background: rgba(185, 28, 28, 0.12);
}

.btn-primary,
.btn-ghost,
.btn-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 32px;
  padding: 0 12px;
  box-sizing: border-box;
  font-size: 13px;
  cursor: pointer;
  border-radius: 9px;
}

.btn-primary {
  font-weight: 700;
  color: #1f2937;
  background: #ebaa28;
  border: 0;
}

.btn-primary:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.btn-ghost {
  color: inherit;
  background: transparent;
  border: 1px solid rgba(var(--text-color-rgb), 0.18);
}

.btn-ghost:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.btn-danger {
  color: #b91c1c;
  background: rgba(185, 28, 28, 0.08);
  border: 1px solid rgba(185, 28, 28, 0.25);
}

.full {
  width: 100%;
  margin-bottom: 9px;
}

.self-end {
  align-self: flex-end;
}

.hint-text {
  margin: 4px 0 10px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--links-color);
}

.detail-actions {
  position: sticky;
  bottom: 0;
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 8px;
  padding: 8px 0 10px;
  background: linear-gradient(rgba(var(--card-color-rgb), 0), rgba(var(--card-color-rgb), 0.92) 24%);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}

.detail-actions .btn-danger {
  margin-left: auto;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 75;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.45);
}

.modal {
  display: flex;
  flex-direction: column;
  width: min(680px, 100%);
  max-height: 84vh;
  padding: 16px;
  overflow: auto;
  /* 与全站 dialog_box 同款背景 / 毛玻璃 */
  background: var(--navbar-bg);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 14px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.modal-head h2 {
  margin: 0;
  font-size: 16px;
}

.modal-state {
  padding: 20px;
  text-align: center;
  color: var(--links-color);
}

.version-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.version-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 4px;
  border-top: 1px solid rgba(var(--text-color-rgb), 0.08);
}

.version-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.version-id {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px;
}

.version-current {
  align-self: flex-start;
  padding: 1px 6px;
  font-size: 10px;
  color: var(--notice-color);
  border: 1px solid var(--notice-color);
  border-radius: 999px;
}

.version-summary {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--links-color);
  text-align: right;
}

.conflict-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.conflict-list li {
  padding: 9px;
  margin-bottom: 8px;
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 9px;
}

.conflict-list li.resolved {
  opacity: 0.55;
}

.conflict-list code {
  font-size: 12px;
}

.conflict-values {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 6px 0;
  font-size: 12px;
  color: var(--links-color);
  word-break: break-all;
}

.conflict-actions {
  display: flex;
  gap: 6px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.search-field {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  margin-bottom: 8px;
  color: var(--links-color);
  background: var(--bg-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.14);
  border-radius: 9px;
}

.search-field input {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text-color);
  background: transparent;
  border: 0;
  outline: none;
}

.add-station-list {
  max-height: 46vh;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.add-station-list li label {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px;
  font-size: 13px;
  cursor: pointer;
  border-radius: 8px;
}

.add-station-list li label:hover {
  background: var(--float-bg);
}

.add-station-list code {
  margin-left: auto;
  font-size: 11px;
  color: var(--links-color);
}

/* 通用弹窗的毛玻璃版本 */
.modal-overlay.is-glass {
  background: rgba(0, 0, 0, 0.4);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}

.is-glass .modal {
  background: rgba(var(--card-color-rgb, 255, 255, 255), 0.78);
  -webkit-backdrop-filter: blur(18px);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(var(--text-color-rgb), 0.14);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
}

.note-field {
  margin-top: 10px;
}

.note-field :deep(.md-editor) {
  margin-top: 6px;
}

@media (max-width: 767px) {
  .edit-page {
    padding: 84px 12px 90px;
  }

  .edit-head h1 {
    font-size: 18px;
  }

  .summary-input {
    flex: 1;
    min-width: 0;
  }

  .edit-grid,
  .edit-grid.no-detail {
    display: flex;
    flex-direction: column;
    height: auto;
  }

  .panel-preview {
    min-height: 380px;
  }

  .panel-list {
    max-height: none;
  }

  .panel-list .list-body {
    max-height: 190px;
  }

  .element-list {
    display: flex;
    gap: 6px;
    overflow-x: auto;
  }

  .element-list li {
    flex: 0 0 auto;
    padding: 6px 10px;
    border: 1px solid rgba(var(--text-color-rgb), 0.12);
    border-radius: 999px;
  }

  .element-meta {
    display: none;
  }

  .panel-detail.is-sheet .detail-body {
    /* 底部留出悬浮邮件按钮的高度，避免压住备注编辑区 */
    padding-bottom: 72px;
  }

  .panel-detail.is-sheet {
    position: fixed;
    right: 0;
    bottom: 0;
    left: 0;
    z-index: 65;
    max-height: 80vh;
    overflow-y: auto;
    overscroll-behavior: contain;
    /* 与全站弹窗 / 导航同款背景与毛玻璃 */
    background: var(--navbar-bg);
    -webkit-backdrop-filter: blur(12px);
    backdrop-filter: blur(12px);
    border-radius: 20px 20px 0 0;
    box-shadow: 0 -12px 40px rgba(0, 0, 0, 0.3);
  }

  /* 底部抽屉滑入 / 滑出（曲线与时长对齐全站 dialog-fade） */
  .sheet-enter-active,
  .sheet-leave-active {
    transition:
      transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
      opacity 0.2s ease;
  }

  .sheet-enter-from,
  .sheet-leave-to {
    opacity: 0;
    transform: translateY(100%);
  }

  @media (prefers-reduced-motion: reduce) {
    .sheet-enter-active,
    .sheet-leave-active {
      transition: none;
    }
  }
}
</style>


<style>
/* 手机编辑抽屉打开时隐藏左下角消息悬浮按钮 */
@media (max-width: 767px) {
  body.transit-sheet-open .message-fab {
    display: none;
  }
}
</style>

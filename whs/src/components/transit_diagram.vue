<script setup>
/**
 * 轨交示意图（SVG 渲染，纯展示 + 点击选中）。
 *
 * 只吃 transitLayout.buildSchematic() 的结果：线路 path、站点坐标、站名。
 * 页面负责取数 / 图例 / 站点卡，编辑页也复用本组件做实时预览。
 *
 * - 站点/线路都可点选，emit('select', { kind: 'station' | 'line', id })；
 * - 缩放按钮带缓动动画，滚轮/拖拽即时；
 * - 只在示意图 bounds 变化时重新适配视野，编辑名称/颜色不会重置缩放。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Crosshair, Minus, Plus } from 'lucide-vue-next'
import { transferArcs } from '../composables/transitLayout'

const props = defineProps({
  schematic: { type: Object, required: true },
  selectedId: { type: String, default: '' },
  hiddenLines: { type: Array, default: () => [] },
  interactive: { type: Boolean, default: true },
  editableLabels: { type: Boolean, default: false },
  locale: { type: String, default: 'zh' },
})
const emit = defineEmits(['select', 'label-move', 'label-reset'])

const svgEl = ref(null)
const containerEl = ref(null)
const hovered = ref(null)
const tooltip = ref(null)
const viewBox = ref({ x: 0, y: 0, w: 800, h: 500 })
let drag = null
let animation = null
let lastBoundsKey = ''
let moved = false
let suppressClick = false
let labelDrag = null
let labelMoved = false

const lines = computed(() => (props.schematic?.lines || [])
  .filter((line) => !props.hiddenLines.includes(line.id)))

const stations = computed(() => props.schematic?.stations || [])

/** 所有线路都被隐藏时，车站降为半透明但仍可点；悬浮时其余元素变灰。 */
function isDimmed(station) {
  if (hovered.value) {
    if (hovered.value.kind === 'station') return station.id !== hovered.value.id
    return !station.lines.includes(hovered.value.id)
  }
  return !station.lines.some((id) => !props.hiddenLines.includes(id))
}

function isLineDimmed(line) {
  if (!hovered.value) return false
  if (hovered.value.kind === 'line') return line.id !== hovered.value.id
  return !(line.stations || []).includes(hovered.value.id)
}

function stationLabel(station) {
  return station.label?.text || station.name?.[props.locale] || station.name?.zh || station.name?.en || station.id
}

function lineLabel(line) {
  return line.name?.[props.locale] || line.name?.zh || line.name?.en || line.id
}

function lineNamesFor(station) {
  return station.lines
    .map((id) => props.schematic.lines.find((item) => item.id === id))
    .filter(Boolean)
    .map((line) => lineLabel(line))
    .join(' · ')
}

function placeTip(event) {
  if (!containerEl.value || !tooltip.value) return
  const rect = containerEl.value.getBoundingClientRect()
  tooltip.value = {
    ...tooltip.value,
    x: Math.min(event.clientX - rect.left + 14, rect.width - 190),
    y: Math.min(event.clientY - rect.top + 14, rect.height - 70),
  }
}

function enterStation(station, event) {
  if (!props.interactive) return
  hovered.value = { kind: 'station', id: station.id }
  tooltip.value = { title: stationLabel(station), sub: lineNamesFor(station), x: 0, y: 0 }
  placeTip(event)
}

function enterLine(line, event) {
  if (!props.interactive) return
  hovered.value = { kind: 'line', id: line.id }
  const unit = props.locale === 'en' ? 'stations' : '站'
  tooltip.value = { title: lineLabel(line), sub: `${(line.stations || []).length} ${unit}`, x: 0, y: 0 }
  placeTip(event)
}

function moveTip(event) {
  if (tooltip.value) placeTip(event)
}

function leaveHover() {
  hovered.value = null
  tooltip.value = null
}

function svgPoint(event) {
  const svg = svgEl.value
  if (!svg) return null
  const pt = svg.createSVGPoint()
  pt.x = event.clientX
  pt.y = event.clientY
  const ctm = svg.getScreenCTM()
  return ctm ? pt.matrixTransform(ctm.inverse()) : null
}

function startLabelDrag(station, event) {
  if (!props.editableLabels || event.button !== 0 || !station.label) return
  const point = svgPoint(event)
  if (!point) return
  event.preventDefault()
  event.stopPropagation()
  labelDrag = {
    id: station.id,
    start: point,
    offsetX: station.label.offsetX || 0,
    offsetY: station.label.offsetY || 0,
  }
  labelMoved = false
  window.addEventListener('pointermove', onLabelDrag)
  window.addEventListener('pointerup', stopLabelDrag, { once: true })
}

function onLabelDrag(event) {
  if (!labelDrag) return
  const point = svgPoint(event)
  if (!point) return
  const dx = Math.round(point.x - labelDrag.start.x)
  const dy = Math.round(point.y - labelDrag.start.y)
  if (Math.abs(dx) > 2 || Math.abs(dy) > 2) labelMoved = true
  emit('label-move', { id: labelDrag.id, dx: labelDrag.offsetX + dx, dy: labelDrag.offsetY + dy })
}

function stopLabelDrag() {
  window.removeEventListener('pointermove', onLabelDrag)
  labelDrag = null
  // 拖完后的 click 由 onStationClick 吃掉；若没有 click，下一帧复位
  if (labelMoved) setTimeout(() => { labelMoved = false }, 0)
}

function onStationClick(station) {
  if (labelMoved) {
    labelMoved = false
    return
  }
  select(station)
}

function stationColor(station) {
  if (!station.lines.length) return station.color
  const visible = station.lines.find((id) => !props.hiddenLines.includes(id))
  const line = props.schematic.lines.find((item) => item.id === (visible || station.lines[0]))
  return line?.color || station.color
}

function dashFor(line) {
  if (line.status === 'building') return '10 7'
  if (line.status === 'planned') return '3 6'
  return ''
}

function boundsKey(bounds) {
  if (!bounds) return ''
  return `${Math.round(bounds.x)},${Math.round(bounds.y)},${Math.round(bounds.width)},${Math.round(bounds.height)}`
}

function fit(animate = false) {
  const bounds = props.schematic?.bounds
  if (!bounds) return
  lastBoundsKey = boundsKey(bounds)
  const target = { x: bounds.x, y: bounds.y, w: bounds.width, h: bounds.height }
  if (animate) tweenTo(target)
  else viewBox.value = target
}

watch(() => boundsKey(props.schematic?.bounds), (key) => {
  // 只有视野范围真的变了才重新适配（改名字、改颜色不会触发）
  if (key && key !== lastBoundsKey) fit()
}, { immediate: true })

function easeOutCubic(t) {
  return 1 - (1 - t) ** 3
}

function tweenTo(target, duration = 200) {
  stopAnimation()
  const from = { ...viewBox.value }
  const startedAt = performance.now()
  const step = (now) => {
    const progress = Math.min((now - startedAt) / duration, 1)
    const eased = easeOutCubic(progress)
    viewBox.value = {
      x: from.x + (target.x - from.x) * eased,
      y: from.y + (target.y - from.y) * eased,
      w: from.w + (target.w - from.w) * eased,
      h: from.h + (target.h - from.h) * eased,
    }
    if (progress < 1) animation = requestAnimationFrame(step)
    else animation = null
  }
  animation = requestAnimationFrame(step)
}

function stopAnimation() {
  if (animation) cancelAnimationFrame(animation)
  animation = null
}

function zoom(factor, clientX, clientY, animate = false) {
  if (!svgEl.value) return
  const rect = svgEl.value.getBoundingClientRect()
  const box = viewBox.value
  const scale = Math.min(Math.max(box.w * factor, 160), 6000)
  const ratio = scale / box.w
  const cx = clientX === undefined ? box.x + box.w / 2 : box.x + ((clientX - rect.left) / rect.width) * box.w
  const cy = clientY === undefined ? box.y + box.h / 2 : box.y + ((clientY - rect.top) / rect.height) * box.h
  const target = {
    x: cx - (cx - box.x) * ratio,
    y: cy - (cy - box.y) * ratio,
    w: scale,
    h: box.h * ratio,
  }
  if (animate) tweenTo(target, 180)
  else viewBox.value = target
}

function onWheel(event) {
  if (!props.interactive) return
  event.preventDefault()
  stopAnimation()
  zoom(event.deltaY > 0 ? 1.12 : 1 / 1.12, event.clientX, event.clientY)
}

function onPointerDown(event) {
  if (!props.interactive || event.button !== 0) return
  stopAnimation()
  moved = false
  drag = { x: event.clientX, y: event.clientY, box: { ...viewBox.value } }
  // 不用 setPointerCapture：捕获到 svg 根节点会让站点/线路的 click 永远不触发
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp, { once: true })
  window.addEventListener('pointercancel', onPointerUp, { once: true })
}

function onPointerMove(event) {
  if (!drag || !svgEl.value) return
  if (Math.abs(event.clientX - drag.x) + Math.abs(event.clientY - drag.y) > 4) moved = true
  const rect = svgEl.value.getBoundingClientRect()
  viewBox.value = {
    ...drag.box,
    x: drag.box.x - ((event.clientX - drag.x) / rect.width) * drag.box.w,
    y: drag.box.y - ((event.clientY - drag.y) / rect.height) * drag.box.h,
  }
}

function onPointerUp() {
  window.removeEventListener('pointermove', onPointerMove)
  // 拖动结束后紧跟的 click 不应被当成“点选”
  if (drag && moved) suppressClick = true
  drag = null
  if (suppressClick) setTimeout(() => { suppressClick = false }, 0)
}

function onClick(event) {
  if (suppressClick) {
    event.stopPropagation()
    event.preventDefault()
  }
}

function select(station) {
  if (props.interactive) emit('select', { kind: 'station', id: station.id })
}

function selectLine(line) {
  if (props.interactive) emit('select', { kind: 'line', id: line.id })
}

onBeforeUnmount(() => {
  drag = null
  stopAnimation()
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
})
</script>

<template>
  <div ref="containerEl" class="transit-diagram">
    <div class="transit-zoom" role="group" aria-label="zoom">
      <button type="button" :aria-label="'zoom in'" @click="zoom(0.8, undefined, undefined, true)"><Plus :size="16" /></button>
      <button type="button" :aria-label="'zoom out'" @click="zoom(1.25, undefined, undefined, true)"><Minus :size="16" /></button>
      <button type="button" :aria-label="'reset'" @click="fit(true)"><Crosshair :size="16" /></button>
    </div>

    <svg
      ref="svgEl"
      class="transit-svg"
      :viewBox="`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`"
      role="img"
      :aria-label="schematic?.title || 'transit'"
      :style="{ cursor: interactive ? 'grab' : 'default' }"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @click.capture="onClick"
    >
      <g class="transit-lines">
        <g
          v-for="line in lines"
          :key="line.id"
          class="transit-line"
          :class="{ 'is-selected': line.id === selectedId, 'is-dim': isLineDimmed(line) }"
          @pointerenter="enterLine(line, $event)"
          @pointermove="moveTip"
          @pointerleave="leaveHover"
        >
          <path
            class="line-hit"
            :d="line.path"
            fill="none"
            stroke="transparent"
            :stroke-width="26"
            stroke-linecap="round"
            @click.stop="selectLine(line)"
          />
          <path
            v-for="(segment, index) in line.segmentPaths"
            :key="`${segment.from}-${segment.to}-${index}`"
            class="line-stroke"
            :d="segment.path"
            fill="none"
            :stroke="line.color"
            :stroke-width="2"
            :stroke-dasharray="dashFor(segment)"
            stroke-linecap="round"
            stroke-linejoin="round"
            @click.stop="selectLine(line)"
          />
        </g>
      </g>

      <g class="transit-stations">
        <TransitionGroup name="station">
        <g
          v-for="station in stations"
          :key="station.id"
          :transform="`translate(${station.sx} ${station.sy})`"
          :class="{
            'is-dim': isDimmed(station),
            'is-selected': station.id === selectedId,
            'is-clickable': interactive,
          }"
          :tabindex="interactive ? 0 : undefined"
          :role="interactive ? 'button' : undefined"
          :aria-label="station.label?.text || station.id"
          @click.stop="onStationClick(station)"
          @keydown.enter.prevent="select(station)"
          @pointerenter="enterStation(station, $event)"
          @pointermove="moveTip"
          @pointerleave="leaveHover"
        >
          <!-- 透明热区：手机上点站名/站点附近都能选中，避免只能靠搜索 -->
          <circle class="station-hit" r="20" fill="transparent" />
          <circle v-if="!station.transfer" class="station-dot" r="5.5" :stroke="stationColor(station)" stroke-width="1.25" />
          <!-- 换乘站：空心圆 + 双向箭头 -->
          <g v-if="station.transfer" class="transfer-arrows">
            <g v-for="(arc, index) in transferArcs(station, props.schematic.lines)" :key="index">
              <path :d="arc.path" fill="none" :stroke="arc.color" stroke-width="1.75" stroke-linecap="round" />
              <path :d="arc.head" :fill="arc.color" stroke="none" />
            </g>
          </g>
          <template v-if="station.label">
            <rect
              class="station-label-hit"
              :class="{ 'is-editable': editableLabels }"
              :x="station.label.hit[0] - station.sx"
              :y="station.label.hit[1] - station.sy"
              :width="station.label.hit[2]"
              :height="station.label.hit[3]"
              rx="4"
              @pointerdown="startLabelDrag(station, $event)"
              @click.stop="onStationClick(station)"
              @dblclick.stop="emit('label-reset', station.id)"
            />
            <text
              :x="station.label.x - station.sx"
              :y="station.label.y - station.sy"
              :text-anchor="station.label.anchor"
              class="station-label"
              :class="{ 'is-editable': editableLabels }"
              @pointerdown="startLabelDrag(station, $event)"
              @click.stop="onStationClick(station)"
              @dblclick.stop="emit('label-reset', station.id)"
            >{{ station.label.text }}</text>
          </template>
        </g>
        </TransitionGroup>
      </g>
    </svg>

    <div v-if="tooltip" class="station-tip" :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }">
      <strong>{{ tooltip.title }}</strong>
      <span v-if="tooltip.sub">{{ tooltip.sub }}</span>
    </div>
  </div>
</template>

<style scoped>
.transit-diagram {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 320px;
  overflow: hidden;
  background:
    radial-gradient(circle at 30% 15%, rgba(var(--text-color-rgb), 0.05), transparent 62%),
    var(--bg-color);
  border-radius: 14px;
}

.transit-svg {
  width: 100%;
  height: 100%;
  touch-action: none;
  user-select: none;
}

.line-hit {
  pointer-events: stroke;
  cursor: pointer;
}

.transit-lines .transit-line {
  transition: opacity 0.15s ease;
}

.transit-line.is-dim {
  opacity: 0.15;
}

.transit-lines .transit-line.is-selected .line-stroke {
  filter: drop-shadow(0 0 6px rgba(0, 0, 0, 0.35));
}

.station-dot {
  fill: var(--bg-color);
}

.transit-stations g {
  outline: none;
}

.transit-stations g.is-clickable {
  cursor: pointer;
}

.station-hit {
  pointer-events: fill;
}

.transit-stations g:focus-visible .station-hit {
  fill: rgba(var(--notice-color), 0.25);
}

.transit-stations g.is-dim {
  opacity: 0.15;
}

.transfer-arrows {
  pointer-events: none;
}

.station-tip {
  position: absolute;
  z-index: 3;
  min-width: 120px;
  max-width: 200px;
  padding: 7px 9px;
  pointer-events: none;
  background: var(--navbar-bg);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(var(--text-color-rgb), 0.14);
  border-radius: 9px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.2);
}

.station-tip strong {
  display: block;
  font-size: 12px;
  font-weight: 700;
}

.station-tip span {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--links-color);
}

/* 站点增删/换色时淡入淡出，避免“突然消失” */
.station-enter-active,
.station-leave-active {
  transition: opacity 0.25s ease;
}

.station-enter-from,
.station-leave-to {
  opacity: 0;
}

.transit-stations g.is-selected .station-dot {
  stroke: var(--notice-color);
  stroke-width: 1.5;
}

.station-label-hit {
  fill: transparent;
  cursor: pointer;
}

.station-label-hit.is-editable,
.station-label.is-editable {
  cursor: move;
}

.station-label {
  font-size: 13px;
  pointer-events: auto;
  cursor: pointer;
  font-weight: 500;
  fill: var(--text-color);
  pointer-events: none;
  paint-order: stroke;
  stroke: var(--bg-color);
  stroke-width: 2px;
  stroke-linejoin: round;
}

.transit-zoom {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.transit-zoom button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: var(--text-color);
  cursor: pointer;
  background: rgba(var(--card-color-rgb, 255, 255, 255), 0.75);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 9px;
  transition: transform 0.12s ease, background 0.15s ease;
}

.transit-zoom button:hover {
  background: var(--float-bg);
}

.transit-zoom button:active {
  transform: scale(0.88);
}

@media (max-width: 767px) {
  .transit-svg {
    /* 手机上允许上下滑动页面，横向拖拽仍可平移示意图 */
    touch-action: pan-y;
  }
}
</style>

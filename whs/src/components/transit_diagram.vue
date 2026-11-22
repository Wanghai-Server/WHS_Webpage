<script setup>
/**
 * 轨交示意图（SVG 渲染，纯展示）。
 *
 * 只吃 transitLayout.buildSchematic() 的结果：线路 path、站点坐标、站名。
 * 页面负责取数 / 图例 / 站点卡，编辑页也复用本组件做实时预览。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  schematic: { type: Object, required: true },
  selectedId: { type: String, default: '' },
  hiddenLines: { type: Array, default: () => [] },
  interactive: { type: Boolean, default: true },
})

const emit = defineEmits(['select'])

const svgEl = ref(null)
const viewBox = ref({ x: 0, y: 0, w: 800, h: 500 })
let drag = null

const lines = computed(() => (props.schematic?.lines || [])
  .filter((line) => !props.hiddenLines.includes(line.id)))

const stations = computed(() => props.schematic?.stations || [])

/** 所有线路都被隐藏时，车站降为半透明但仍可点。 */
function isDimmed(station) {
  return !station.lines.some((id) => !props.hiddenLines.includes(id))
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

function fit() {
  const bounds = props.schematic?.bounds
  if (!bounds) return
  viewBox.value = { x: bounds.x, y: bounds.y, w: bounds.width, h: bounds.height }
}

watch(() => props.schematic, fit, { immediate: true })

function zoom(factor, clientX, clientY) {
  if (!svgEl.value) return
  const rect = svgEl.value.getBoundingClientRect()
  const box = viewBox.value
  const scale = Math.min(Math.max(box.w * factor, 160), 6000)
  const ratio = scale / box.w
  const cx = clientX === undefined ? box.x + box.w / 2 : box.x + ((clientX - rect.left) / rect.width) * box.w
  const cy = clientY === undefined ? box.y + box.h / 2 : box.y + ((clientY - rect.top) / rect.height) * box.h
  viewBox.value = {
    x: cx - (cx - box.x) * ratio,
    y: cy - (cy - box.y) * ratio,
    w: scale,
    h: box.h * ratio,
  }
}

function onWheel(event) {
  if (!props.interactive) return
  event.preventDefault()
  zoom(event.deltaY > 0 ? 1.12 : 1 / 1.12, event.clientX, event.clientY)
}

function onPointerDown(event) {
  if (!props.interactive || event.button !== 0) return
  drag = { x: event.clientX, y: event.clientY, box: { ...viewBox.value } }
  svgEl.value?.setPointerCapture?.(event.pointerId)
}

function onPointerMove(event) {
  if (!drag || !svgEl.value) return
  const rect = svgEl.value.getBoundingClientRect()
  viewBox.value = {
    ...drag.box,
    x: drag.box.x - ((event.clientX - drag.x) / rect.width) * drag.box.w,
    y: drag.box.y - ((event.clientY - drag.y) / rect.height) * drag.box.h,
  }
}

function onPointerUp() {
  drag = null
}

function select(station) {
  if (props.interactive) emit('select', station)
}

onBeforeUnmount(() => {
  drag = null
})
</script>

<template>
  <div class="transit-diagram">
    <div class="transit-zoom">
      <button type="button" :aria-label="'zoom in'" @click="zoom(1 / 1.2)">+</button>
      <button type="button" :aria-label="'zoom out'" @click="zoom(1.2)">−</button>
      <button type="button" :aria-label="'reset'" @click="fit">⌂</button>
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
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointerleave="onPointerUp"
    >
      <g class="transit-lines">
        <path
          v-for="line in lines"
          :key="line.id"
          :d="line.path"
          fill="none"
          :stroke="line.color"
          :stroke-width="line.type === 'metro' ? 7 : 5"
          :stroke-dasharray="dashFor(line)"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </g>

      <g class="transit-stations">
        <g
          v-for="station in stations"
          :key="station.id"
          :transform="`translate(${station.x} ${station.y})`"
          :class="{
            'is-dim': isDimmed(station),
            'is-selected': station.id === selectedId,
            'is-clickable': interactive,
          }"
          :tabindex="interactive ? 0 : undefined"
          :role="interactive ? 'button' : undefined"
          :aria-label="station.label?.text || station.id"
          @click.stop="select(station)"
          @keydown.enter.prevent="select(station)"
        >
          <circle v-if="station.transfer" class="station-ring" r="10" fill="none" stroke-width="3" :stroke="stationColor(station)" />
          <circle class="station-dot" r="6" :fill="stationColor(station)" stroke-width="2" />
          <text
            v-if="station.label"
            :x="station.label.x - station.x"
            :y="station.label.y - station.y"
            :text-anchor="station.label.anchor"
            class="station-label"
          >{{ station.label.text }}</text>
        </g>
      </g>
    </svg>
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

.station-ring,
.station-dot {
  stroke: var(--card-color);
}

.transit-stations g {
  outline: none;
}

.transit-stations g.is-clickable {
  cursor: pointer;
}

.transit-stations g.is-dim {
  opacity: 0.25;
}

.transit-stations g.is-selected .station-dot {
  stroke: var(--notice-color);
  stroke-width: 3;
}

.station-label {
  font-size: 13px;
  font-weight: 500;
  fill: var(--text-color);
  pointer-events: none;
  paint-order: stroke;
  stroke: var(--bg-color);
  stroke-width: 3px;
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
  width: 30px;
  height: 30px;
  font-size: 15px;
  line-height: 1;
  color: var(--text-color);
  cursor: pointer;
  background: var(--card-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 8px;
}

.transit-zoom button:hover {
  background: var(--float-bg);
}
</style>

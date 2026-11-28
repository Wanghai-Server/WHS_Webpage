<script setup>
/**
 * 从 BlueMap 取点（P4）。
 *
 * 桌面是居中弹窗、手机是底部抽屉，里面嵌 `/map3d/` 的 iframe（同源）。
 * 取坐标走 BlueMap 自己维护的 URL hash：用户把视角移动到目标位置后，
 * hash 里就是当前相机 `mapId:x:y:z:...`，编辑器直接读它作为候选坐标；
 * 读不到（iframe 未就绪 / BlueMap 没部署）就提示手动填写。
 */
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { MapPin, X } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'

const props = defineProps({
  open: { type: Boolean, default: false },
  initial: { type: Object, default: () => ({ x: 0, z: 0 }) },
})

const emit = defineEmits(['close', 'pick'])
const { t } = useI18n()
const { state: authState } = useAuth()
const viewerPath = ref('/map3d/')

const frameEl = ref(null)
const candidate = ref(null)
const failed = ref(false)
const loaded = ref(false)
const frameReady = ref(false)
const viewerReady = ref(false)
const manual = reactive({ x: 0, z: 0, y: 80 })
let timer = null
let failTimer = null
let probeTimer = null
let probeTries = 0
let initialHash = ''

async function loadViewer() {
  const headers = authState.token ? { Authorization: `Bearer ${authState.token}` } : {}
  try {
    const res = await fetch('/api/map/config', { headers })
    const body = await res.json().catch(() => ({}))
    if (body.viewer) viewerPath.value = body.viewer
  } catch {
    // 拿不到就退回默认入口
  }
  // 不用 HEAD 探活阻断 iframe：部分反代不支持 HEAD / 鉴权时序不同，
  // 错误页也会触发 load，交给 onLoad 的 canvas 探测与超时兜底处理。
  viewerReady.value = true
  return true
}

const src = computed(() => {
  const x = Number(props.initial?.x) || 0
  const z = Number(props.initial?.z) || 0
  const y = Number(props.initial?.y) || 80
  return `${viewerPath.value}#world:${x}:${y + 40}:${z}:200:0:1.1:0:0:perspective`
})

function readHash() {
  try {
    return frameEl.value?.contentWindow?.location?.hash || ''
  } catch {
    return ''
  }
}

function parseHash() {
  try {
    const hash = readHash()
    const body = hash.replace(/^#/, '')
    if (!body) return
    // 初始 hash 是相机在站点上方的位置，不代表用户选点：跳过它
    if (body === initialHash) return
    const parts = body.split(':')
    if (parts.length < 4) return
    const x = Number(parts[1])
    const y = Number(parts[2])
    const z = Number(parts[3])
    if (![x, y, z].every(Number.isFinite)) return
    candidate.value = { x: Math.round(x), y: Math.round(y), z: Math.round(z) }
    manual.x = candidate.value.x
    manual.z = candidate.value.z
    manual.y = candidate.value.y
    failed.value = false
  } catch {
    // 跨域或 iframe 还没加载完，交给下一轮轮询
  }
}

function startPolling() {
  stopPolling()
  timer = setInterval(parseHash, 400)
}

function stopPolling() {
  if (timer) clearInterval(timer)
  timer = null
}

function frameHasCanvas() {
  try {
    const doc = frameEl.value?.contentDocument
    if (!doc) return null // 跨域：无法探测
    return !!doc.querySelector('canvas')
  } catch {
    return null
  }
}

function confirmReady() {
  loaded.value = true
  frameReady.value = true
  if (failTimer) clearTimeout(failTimer)
  if (probeTimer) clearTimeout(probeTimer)
  initialHash = readHash().replace(/^#/, '')
  startPolling()
}

function fail() {
  failed.value = true
  loaded.value = true
  if (failTimer) clearTimeout(failTimer)
  if (probeTimer) clearTimeout(probeTimer)
}

function probeCanvas() {
  const hasCanvas = frameHasCanvas()
  if (hasCanvas === null || hasCanvas === true) {
    // 跨域无法探测，或 BlueMap 已经画出 canvas：按就绪处理
    confirmReady()
    return
  }
  probeTries += 1
  if (probeTries >= 30) {
    // 同源但 12 秒仍没有 canvas：多半是 502/401 错误页；保留轮询，
    // 地图晚一点渲染出来时仍能继续读取 hash
    fail()
    return
  }
  probeTimer = setTimeout(probeCanvas, 400)
}

function onLoad() {
  // load 事件错误页也会触发：不直接判定成功，先探测 canvas；
  // 同时马上开始轮询 hash，BlueMap 渲染慢时也能接住坐标
  initialHash = readHash().replace(/^#/, '')
  probeTries = 0
  if (probeTimer) clearTimeout(probeTimer)
  probeTimer = setTimeout(probeCanvas, 300)
  startPolling()
  try {
    // 点击地图时 BlueMap 会更新 hash；点击后再补一次解析，覆盖拖动/点击两种交互
    frameEl.value?.contentDocument?.addEventListener('pointerup', () => {
      setTimeout(parseHash, 120)
      setTimeout(parseHash, 500)
    })
  } catch {
    // 跨域时无法挂监听，交给轮询
  }
}

function onError() {
  fail()
}

function useManual() {
  if (![manual.x, manual.z, manual.y].every(Number.isFinite)) return
  candidate.value = { x: Math.round(manual.x), z: Math.round(manual.z), y: Math.round(manual.y) }
  failed.value = false
}

function confirm() {
  if (!candidate.value) return
  emit('pick', { ...candidate.value })
}

watch(() => props.open, async (open) => {
  if (open) {
    candidate.value = null
    failed.value = false
    loaded.value = false
    frameReady.value = false
    viewerReady.value = false
    initialHash = ''
    manual.x = Number(props.initial?.x) || 0
    manual.z = Number(props.initial?.z) || 0
    manual.y = Number(props.initial?.y) || 80
    // 12 秒还没确认地图可用，就提示手动填写
    failTimer = setTimeout(() => {
      if (!frameReady.value) fail()
    }, 12000)
    const ok = await loadViewer()
    if (!ok) {
      fail()
      return
    }
    await nextTick()
    // iframe 的 src 在 loadViewer 之后才设置：先写 /api/map/config 的鉴权 Cookie，
    // 避免首帧请求 /map3d/ 时 401
    frameReady.value = true
  } else {
    stopPolling()
    if (failTimer) clearTimeout(failTimer)
    if (probeTimer) clearTimeout(probeTimer)
  }
})

onBeforeUnmount(() => {
  stopPolling()
  if (failTimer) clearTimeout(failTimer)
  if (probeTimer) clearTimeout(probeTimer)
})
</script>

<template>
  <div v-if="open" class="picker-overlay" @click.self="emit('close')">
    <section class="picker-panel" role="dialog" aria-modal="true" :aria-label="t('transit.edit.pickTitle')">
      <header class="picker-head">
        <h2>{{ t('transit.edit.pickTitle') }}</h2>
        <button type="button" class="picker-close" :aria-label="t('transit.edit.cancel')" @click="emit('close')">
          <X :size="18" />
        </button>
      </header>

      <p class="picker-hint">{{ t('transit.edit.pickHint') }}</p>

      <div class="picker-manual">
        <span>{{ t('transit.edit.pickManual') }}</span>
        <label>X <input v-model.number="manual.x" class="manual-input" type="number" /></label>
        <label>Z <input v-model.number="manual.z" class="manual-input" type="number" /></label>
        <label>Y <input v-model.number="manual.y" class="manual-input" type="number" /></label>
        <button type="button" class="btn-ghost" @click="useManual">{{ t('transit.edit.pickManualUse') }}</button>
      </div>

      <div class="picker-frame-wrap">
        <iframe
          v-if="frameReady"
          ref="frameEl"
          class="picker-frame"
          :src="src"
          :title="t('transit.edit.pickTitle')"
          @load="onLoad"
          @error="onError"
        ></iframe>
      </div>

      <footer class="picker-foot">
        <span v-if="candidate" class="picker-candidate">
          <MapPin :size="14" aria-hidden="true" />
          X {{ candidate.x }} / Z {{ candidate.z }} / Y {{ candidate.y }}
        </span>
        <span v-else class="picker-candidate is-empty">{{ failed ? t('transit.edit.pickFailed') : t('transit.edit.pickWaiting') }}</span>

        <div class="picker-actions">
          <button type="button" class="btn-ghost" @click="emit('close')">{{ t('transit.edit.cancel') }}</button>
          <button type="button" class="btn-primary" :disabled="!candidate" @click="confirm">
            {{ t('transit.edit.pickUse') }}
          </button>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.picker-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.5);
}

.picker-panel {
  display: flex;
  flex-direction: column;
  width: min(1040px, 100%);
  height: min(760px, 100%);
  overflow: hidden;
  background: var(--card-color);
  color: var(--text-color);
  border: 1px solid rgba(var(--text-color-rgb), 0.12);
  border-radius: 16px;
}

.picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--text-color-rgb), 0.1);
}

.picker-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.picker-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: inherit;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 8px;
}

.picker-close:hover {
  background: var(--float-bg);
}

.picker-hint {
  margin: 0;
  padding: 8px 16px;
  font-size: 12px;
  color: var(--links-color);
  border-bottom: 1px solid rgba(var(--text-color-rgb), 0.08);
}

.picker-manual {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding: 8px 16px;
  font-size: 12px;
  color: var(--links-color);
  border-bottom: 1px solid rgba(var(--text-color-rgb), 0.08);
}

.picker-manual label {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.manual-input {
  width: 80px;
  height: 30px;
  padding: 0 8px;
  color: var(--text-color);
  background: rgba(var(--text-color-rgb), 0.06);
  border: 1px solid rgba(var(--text-color-rgb), 0.16);
  border-radius: 7px;
}

.picker-frame-wrap {
  flex: 1;
  min-height: 0;
  background: var(--bg-color);
}

.picker-frame {
  width: 100%;
  height: 100%;
  border: 0;
}

.picker-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-top: 1px solid rgba(var(--text-color-rgb), 0.1);
}

.picker-candidate {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-family: ui-monospace, Menlo, monospace;
}

.picker-candidate.is-empty {
  color: var(--links-color);
  font-family: inherit;
}

.picker-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.btn-ghost,
.btn-primary {
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  border-radius: 9px;
}

.btn-ghost {
  color: inherit;
  background: transparent;
  border: 1px solid rgba(var(--text-color-rgb), 0.2);
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

@media (max-width: 767px) {
  .picker-overlay {
    align-items: flex-end;
    padding: 0;
  }

  .picker-panel {
    width: 100%;
    height: 92vh;
    border-radius: 20px 20px 0 0;
  }
}
</style>

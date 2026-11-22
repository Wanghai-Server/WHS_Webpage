<script setup>
/**
 * 从 BlueMap 取点（P4）。
 *
 * 桌面是居中弹窗、手机是底部抽屉，里面嵌 `/map3d/` 的 iframe（同源）。
 * 取坐标走 BlueMap 自己维护的 URL hash：用户把视角移动到目标位置后，
 * hash 里就是当前相机 `mapId:x:y:z:...`，编辑器直接读它作为候选坐标；
 * 读不到（iframe 未就绪 / BlueMap 没部署）就提示手动填写。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
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
let timer = null

async function loadViewer() {
  try {
    const headers = authState.token ? { Authorization: `Bearer ${authState.token}` } : {}
    const res = await fetch('/api/map/config', { headers })
    const body = await res.json().catch(() => ({}))
    if (body.viewer) viewerPath.value = body.viewer
  } catch {
    // 拿不到就退回默认入口
  }
}

const src = computed(() => {
  const x = Number(props.initial?.x) || 0
  const z = Number(props.initial?.z) || 0
  const y = Number(props.initial?.y) || 80
  return `${viewerPath.value}#world:${x}:${y + 40}:${z}:200:0:1.1:0:0:perspective`
})

function parseHash() {
  try {
    const hash = frameEl.value?.contentWindow?.location?.hash || ''
    const body = hash.replace(/^#/, '')
    if (!body) return
    const parts = body.split(':')
    if (parts.length < 4) return
    const x = Number(parts[1])
    const y = Number(parts[2])
    const z = Number(parts[3])
    if (![x, y, z].every(Number.isFinite)) return
    candidate.value = { x: Math.round(x), y: Math.round(y), z: Math.round(z) }
    failed.value = false
  } catch {
    // 跨域或 iframe 还没加载完，交给下一轮轮询
  }
}

function startPolling() {
  stopPolling()
  timer = setInterval(parseHash, 700)
}

function stopPolling() {
  if (timer) clearInterval(timer)
  timer = null
}

function onLoad() {
  parseHash()
  startPolling()
}

function confirm() {
  if (!candidate.value) return
  emit('pick', { ...candidate.value })
}

watch(() => props.open, (open) => {
  if (open) {
    candidate.value = null
    failed.value = false
    loadViewer()
  } else {
    stopPolling()
  }
})

onBeforeUnmount(stopPolling)
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

      <div class="picker-frame-wrap">
        <iframe
          ref="frameEl"
          class="picker-frame"
          :src="src"
          :title="t('transit.edit.pickTitle')"
          @load="onLoad"
        ></iframe>
      </div>

      <footer class="picker-foot">
        <span v-if="candidate" class="picker-candidate">
          <MapPin :size="14" aria-hidden="true" />
          X {{ candidate.x }} / Z {{ candidate.z }} / Y {{ candidate.y }}
        </span>
        <span v-else class="picker-candidate is-empty">{{ t('transit.edit.pickWaiting') }}</span>

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

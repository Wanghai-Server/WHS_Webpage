<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, ExternalLink } from 'lucide-vue-next'

import { useTips } from '../composables/useTips'

// 可复用的玩家信息悬浮窗组件：
// 展示玩家名字 + 可鼠标旋转的 3D 完整模型（skinview3d，皮肤来自 mc-heads），
// 并提供"查看主页"跳转：先向后端检查 player_name 是否存在，不存在时用
// tips 提示；存在时再向后端 /api/user/by_player_name/{playerName} 发起
// 查找请求，后端 301 到 /user/{uid}，浏览器跟随跳转。
// 使用方需放在 <Teleport to="body"> 中，并通过 props 传入玩家信息。
const props = defineProps({
  playerName: { type: String, required: true },
  displayName: { type: String, default: '' },
})

const emit = defineEmits(['close'])

const { t } = useI18n()
const { showTip } = useTips()

const canvasRef = ref(null)
const modelLoading = ref(true) // 皮肤/渲染库加载期间显示 spinner
let viewer = null

const skinUrl = `https://mc-heads.net/skin/${encodeURIComponent(props.playerName)}`

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = resolve
    img.onerror = reject
    img.src = url
  })
}

async function initViewer() {
  if (!canvasRef.value) return
  modelLoading.value = true
  try {
    // 并行：懒加载 3D 渲染库 + 预加载皮肤纹理（加载中提示真实反映进度）
    const [mod] = await Promise.all([import('skinview3d'), loadImage(skinUrl)])
    const { SkinViewer } = mod
    viewer = new SkinViewer({
      canvas: canvasRef.value,
      width: 320,
      height: 400,
      skin: skinUrl,
      fov: 50,
      zoom: 0.55, // 全身展示，头顶留出边距
      enableControls: true, // 鼠标拖动旋转查看
      autoRotate: true, // 未交互时缓慢自转
    })
  } catch (e) {
    console.warn('[player_info] 3D 模型初始化失败:', e)
  } finally {
    modelLoading.value = false
  }
}

// 跳转主页：先检查玩家是否存在（不存在则 tips 提示，避免跳到看不懂的 404 页面）；
// 存在时按规格向后端发送查找请求，后端 301 到 /user/{uid}，浏览器跟随跳转
async function goToProfile() {
  try {
    const res = await fetch(
      `/api/user/player_name_exists?player_name=${encodeURIComponent(props.playerName)}`
    )
    const data = await res.json().catch(() => null)
    if (res.ok && data && data.exists === false) {
      showTip('error', t('playerInfo.notFound'))
      return
    }
  } catch (e) {
    console.warn('[player_info] 玩家存在性检查失败，直接尝试跳转:', e)
  }
  window.location.assign(`/api/user/by_player_name/${encodeURIComponent(props.playerName)}`)
}

function handleKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  initViewer()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  if (viewer) {
    viewer.dispose()
    viewer = null
  }
})
</script>

<template>
  <div class="player-modal-overlay" @click.self="emit('close')">
    <div class="player-modal dialog">
      <div class="player-modal-head">
        <h3>{{ displayName || playerName }}</h3>
        <button
          type="button"
          class="player-modal-close"
          :aria-label="t('playerInfo.close')"
          @click="emit('close')"
        >
          <X :size="20" />
        </button>
      </div>

      <div class="player-modal-body">
        <canvas ref="canvasRef" class="player-model-canvas"></canvas>
        <div v-if="modelLoading" class="player-model-loading">
          <span class="player-model-spinner"></span>
        </div>
      </div>

      <div class="player-modal-foot">
        <button type="button" class="gold-btn" @click="goToProfile">
          {{ t('playerInfo.viewProfile') }}
          <ExternalLink :size="16" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

/* .dialog 类复用 style.css 的 dialog-fade 弹出动画 */
/* 面板采用全站毛玻璃惯例：半透明 navbar 背景 + 12px 模糊 */
.player-modal {
  width: min(420px, 100%);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.3);
}

.player-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.player-modal-head h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  color: var(--text-color);
  word-break: break-all;
}

.player-modal-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
}

.player-modal-close:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.player-modal-body {
  position: relative;
  flex: 1;
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(11, 29, 58, 0.06), rgba(11, 29, 58, 0.12));
}

.player-model-canvas {
  display: block;
  width: 100%;
  max-width: 320px;
  height: auto;
  aspect-ratio: 320 / 400;
  cursor: grab;
}

.player-model-canvas:active {
  cursor: grabbing;
}

/* 加载遮罩 + spinner（皮肤/渲染库加载期间覆盖在画布上） */
.player-model-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(11, 29, 58, 0.2);
}

.player-model-spinner {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border: 3px solid rgba(235, 170, 40, 0.25);
  border-top-color: #ebaa28;
  border-radius: 50%;
  animation: player-spin 0.8s linear infinite;
}

@keyframes player-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .player-model-spinner {
    animation-duration: 1.6s;
  }
}

.player-modal-foot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid rgba(148, 163, 184, 0.15);
}

.gold-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 32px;
  border: none;
  border-radius: 999px;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-size: 15px;
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

@media (max-width: 480px) {
  .player-modal-body {
    min-height: 280px;
  }
}
</style>

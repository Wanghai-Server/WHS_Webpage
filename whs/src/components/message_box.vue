<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { animate } from 'animejs'

const { t } = useI18n()
const emit = defineEmits(['close'])

// 消息列表（暂时为空）
// 后续从后端 GET /api/message/{user_id} 获取并填充，当前直接 pass（不实现）
const messages = ref([])

const overlayRef = ref(null)
const boxRef = ref(null)

// 计算消息按钮中心相对盒子的位置，作为弹出/收起动画的原点
function getButtonOrigin() {
  const box = boxRef.value
  const fab = document.querySelector('.message-fab')
  if (!box || !fab) {
    return { x: '50%', y: '50%' }
  }
  const fabRect = fab.getBoundingClientRect()
  const boxRect = box.getBoundingClientRect()
  return {
    x: fabRect.left + fabRect.width / 2 - boxRect.left,
    y: fabRect.top + fabRect.height / 2 - boxRect.top
  }
}

onMounted(() => {
  const box = boxRef.value
  const overlay = overlayRef.value

  // 打开动画：盒子从消息按钮处弹出到屏幕中央（带弹性）
  if (box) {
    const { x, y } = getButtonOrigin()
    box.style.transformOrigin = `${x}px ${y}px`
    animate(box, {
      scale: [0, 1],
      opacity: [0, 1],
      duration: 450,
      ease: 'outCubic'
    })
  }
  if (overlay) {
    animate(overlay, { opacity: [0, 1], duration: 300, ease: 'outQuad' })
  }

  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})

function handleKeydown(event) {
  if (event.key === 'Escape') close()
}

function close() {
  const box = boxRef.value
  const overlay = overlayRef.value

  if (overlay) {
    animate(overlay, { opacity: [1, 0], duration: 250, ease: 'outQuad' })
  }
  if (!box) {
    emit('close')
    return
  }

  // 关闭动画：盒子缩回消息按钮处，动画结束后再真正移除
  animate(box, {
    scale: [1, 0],
    opacity: [1, 0],
    duration: 250,
    ease: 'inQuad',
    onComplete: () => emit('close')
  })
}

// 暴露 close 方法，供父组件（消息图标）在图标变叉后触发关闭
defineExpose({ close })
</script>

<template>
  <Teleport to="body">
    <div class="message-overlay" ref="overlayRef" @click.self="close">
      <div class="message-box" ref="boxRef">
        <header class="message-head">
          <h2>{{ t('message.title') }}</h2>
        </header>

        <div class="message-body">
          <p v-if="messages.length === 0" class="message-empty">{{ t('message.empty') }}</p>
          <ul v-else class="message-list">
            <li v-for="msg in messages" :key="msg.id">{{ msg.content }}</li>
          </ul>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.message-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
}

.message-box {
  width: 80%;
  height: 80vh;
  max-width: 92vw;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  color: var(--text-color);
  border-radius: 16px;
  overflow: hidden;
}

.message-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--links-color);
}

.message-head h2 {
  margin: 0;
  font-size: 20px;
}

.message-body {
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow-y: auto;
}

.message-empty {
  margin: 24px 0;
  text-align: center;
  color: var(--links-color);
}

.message-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.message-list li {
  padding: 12px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.message-list li:last-child {
  border-bottom: none;
}
</style>

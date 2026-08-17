<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import { Info, TriangleAlert, CircleX } from 'lucide-vue-next'
import { useTips } from '../composables/useTips'

const { state } = useTips()

// 事件等级 -> 图标
const iconMap = {
  info: Info,
  warning: TriangleAlert,
  error: CircleX,
}

const GAP = 10 // 与样式中的间距一致

// 每个 tip 的纵向偏移（绝对定位 translateY），由元素真实高度累计计算
const offsets = ref({})

async function updateOffsets() {
  await nextTick()
  // 按文档顺序（= 队列顺序）测量，累计每个 tip 的偏移
  const els = [...document.querySelectorAll('.tips-container .tip')]
  const next = {}
  let y = 0
  for (const el of els) {
    next[Number(el.dataset.id)] = y
    y += el.offsetHeight + GAP
  }
  offsets.value = next
}

// 队列长度变化（新增 / 移除）时重算偏移，其余 tip 由 transform 过渡平滑滑动
watch(() => state.tips.length, updateOffsets)
onMounted(updateOffsets)
</script>

<template>
  <Teleport to="body">
    <div class="tips-container">
      <div
        v-for="tip in state.tips"
        :key="tip.id"
        :data-id="tip.id"
        class="tip"
        :class="[tip.type, { leaving: tip.leaving }]"
        :style="{ '--y': `${offsets[tip.id] ?? 0}px` }"
      >
        <component :is="iconMap[tip.type]" :size="20" class="tip-icon" />
        <span class="tip-content">{{ tip.content }}</span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.tips-container {
  position: fixed;
  top: 72px; /* 导航栏(16px 顶部 + 48px 高) 下方 */
  left: 0;
  right: 0;
  z-index: 99999; /* 全局最高层：任何对话框(9500)/弹窗之上，提示永不被遮挡 */
  pointer-events: none;
}

.tip {
  position: absolute;
  top: 0;
  left: 50%;
  --y: 0px;
  transform: translateX(-50%) translateY(var(--y));
  /* 偏移变化（队列重排）时的平滑滑动 */
  transition: transform 0.35s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;

  display: flex;
  align-items: center;
  gap: 10px;
  width: fit-content;
  max-width: 768px;
  min-height: 48px;
  padding: 12px 16px;
  box-sizing: border-box;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: var(--navbar-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  color: var(--text-color);

  /* 进入动画：从当前偏移上方滑入 + 淡入 */
  animation: tip-in 0.3s ease;
}

@keyframes tip-in {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(calc(var(--y) - 16px));
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(var(--y));
  }
}

/* 离开：向下轻微坠落缩放 + 淡出（forwards 保持到移除） */
.tip.leaving {
  animation: tip-out 0.3s ease forwards;
}

@keyframes tip-out {
  to {
    opacity: 0;
    transform: translateX(-50%) translateY(calc(var(--y) + 12px)) scale(0.95);
  }
}

.tip-icon {
  flex-shrink: 0;
}

/* 事件等级配色 */
.tip.info .tip-icon {
  color: #3b82f6;
}

.tip.warning .tip-icon {
  color: #f59e0b;
}

.tip.error .tip-icon {
  color: #e5484d;
}

.tip-content {
  word-break: break-word;
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.5;
}
</style>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'

// 可复用的 Tabs 导航组件（下滑线式）：
// 激活项下方有一条金色下划线，切换时下划线平滑滑动到对应标签。
// 通过 v-model 双向绑定激活 key；items 为 [{key, label}]。
const props = defineProps({
  items: { type: Array, default: () => [] }, // [{ key, label }]
  modelValue: { type: String, default: '' }, // 当前激活的 key
})

const emit = defineEmits(['update:modelValue'])

const barRef = ref(null)
const indicatorRef = ref(null)
let resizeObserver = null

// 把指示器移动到当前激活标签的位置（宽度 + 偏移）
function moveIndicator() {
  const bar = barRef.value
  const indicator = indicatorRef.value
  if (!bar || !indicator) return
  const buttons = bar.querySelectorAll('.tabs-item')
  const index = props.items.findIndex((it) => it.key === props.modelValue)
  const btn = buttons[Math.max(0, index)] || buttons[0]
  if (!btn) return
  indicator.style.width = `${btn.offsetWidth}px`
  indicator.style.transform = `translateX(${btn.offsetLeft}px)`
}

watch(() => props.modelValue, () => nextTick(moveIndicator))
// 标签内容变化（如切换语言导致文案变长）时重新定位
watch(() => props.items, () => nextTick(moveIndicator), { deep: true })

onMounted(() => {
  nextTick(moveIndicator)
  // 容器尺寸变化（语言切换 / 字体加载 / 视口变化）时保持对齐
  if (typeof ResizeObserver !== 'undefined' && barRef.value) {
    resizeObserver = new ResizeObserver(() => moveIndicator())
    resizeObserver.observe(barRef.value)
  }
})

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
})

function onTabClick(key) {
  if (key !== props.modelValue) {
    emit('update:modelValue', key)
  }
}
</script>

<template>
  <nav ref="barRef" class="tabs" role="tablist">
    <button
      v-for="item in items"
      :key="item.key"
      type="button"
      class="tabs-item"
      :class="{ active: item.key === modelValue }"
      role="tab"
      :aria-selected="item.key === modelValue"
      @click="onTabClick(item.key)"
    >{{ item.label }}</button>
    <span ref="indicatorRef" class="tabs-indicator" aria-hidden="true"></span>
  </nav>
</template>

<style scoped>
.tabs {
  position: relative;
  display: inline-flex;
  gap: 4px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  max-width: 100%;
}

.tabs-item {
  position: relative;
  padding: 10px 18px;
  border: none;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.2s ease;
}

.tabs-item:hover {
  color: var(--text-color);
}

.tabs-item.active {
  color: var(--text-color);
}

/* 金色下滑线指示器：盖在容器底边上，切换时平滑滑动 */
.tabs-indicator {
  position: absolute;
  bottom: -1px;
  left: 0;
  height: 3px;
  border-radius: 999px;
  background: #ebaa28;
  transition:
    transform 0.3s cubic-bezier(0.22, 1, 0.36, 1),
    width 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}

/* 标签过多时允许横向滚动（隐藏滚动条） */
@media (max-width: 768px) {
  .tabs {
    overflow-x: auto;
    scrollbar-width: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tabs-indicator {
    transition: none;
  }
}
</style>

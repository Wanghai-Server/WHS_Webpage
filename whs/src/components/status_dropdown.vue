<script setup>
/**
 * 通用状态下拉选择器（自定义样式，替代原生 select）。
 *
 * - 支持三种外观：pill（搜索栏同款胶囊）、chip（表格内的小状态标签）、action（详情页操作按钮）；
 * - 菜单通过 Teleport 渲染到 body 并使用 fixed 定位，避免被表格/面板的 overflow 裁剪，
 *   同时自动限制在视口内，手机端不会超出屏幕；
 * - 点击外部 / Esc 关闭，滚动或窗口尺寸变化时跟随按钮重新定位。
 */
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] }, // [{ value, label }]
  variant: { type: String, default: 'pill' }, // 'pill' | 'chip' | 'action'
  ariaLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const btnRef = ref(null)
const menuRef = ref(null)
const menuStyle = ref({ top: '0px', left: '0px', minWidth: '140px' })

const current = computed(() => {
  return props.options.find((o) => o.value === props.modelValue) || props.options[0] || { value: '', label: '' }
})

async function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (!open.value) return
  await nextTick()
  await positionMenu()
}

async function positionMenu() {
  const btn = btnRef.value
  const menu = menuRef.value
  if (!btn || !menu) return
  const rect = btn.getBoundingClientRect()
  const minWidth = Math.max(Math.round(rect.width), 140)

  // 第一遍：先按按钮位置放置并写入最小宽度，让菜单完成布局
  menuStyle.value = {
    top: `${Math.round(rect.bottom + 6)}px`,
    left: `${Math.round(rect.left)}px`,
    minWidth: `${minWidth}px`,
  }
  await nextTick()

  // 第二遍：按实际菜单尺寸修正，保证不超出视口（必要时向上翻转）
  const menuRect = menu.getBoundingClientRect()
  const menuWidth = menuRect.width || minWidth
  const menuHeight = menuRect.height
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight

  let left = Math.min(rect.right - menuWidth, viewportWidth - menuWidth - 8)
  left = Math.max(8, left)

  let top = rect.bottom + 6
  if (top + menuHeight > viewportHeight - 8 && rect.top - menuHeight - 6 >= 8) {
    top = rect.top - menuHeight - 6
  }
  top = Math.max(8, top)

  menuStyle.value = {
    top: `${Math.round(top)}px`,
    left: `${Math.round(left)}px`,
    minWidth: `${minWidth}px`,
  }
}

function choose(option) {
  open.value = false
  if (option.value !== props.modelValue) emit('update:modelValue', option.value)
}

function onDocumentClick(event) {
  if (!open.value) return
  if (btnRef.value && btnRef.value.contains(event.target)) return
  if (menuRef.value && menuRef.value.contains(event.target)) return
  open.value = false
}

function onKeydown(event) {
  if (event.key === 'Escape') open.value = false
}

function onReposition() {
  if (open.value) positionMenu()
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('scroll', onReposition, true)
  window.addEventListener('resize', onReposition)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('scroll', onReposition, true)
  window.removeEventListener('resize', onReposition)
})
</script>

<template>
  <div class="sd" :class="[`sd-${variant}`, { 'sd-open': open }]">
    <button
      ref="btnRef"
      type="button"
      class="sd-btn"
      :class="{ open, [`is-${modelValue}`]: variant === 'chip' }"
      :disabled="disabled"
      :aria-label="ariaLabel"
      aria-haspopup="listbox"
      :aria-expanded="open"
      @click="toggle"
    >
      <span class="sd-value">{{ current.label }}</span>
      <ChevronDown :size="variant === 'chip' ? 13 : 16" class="sd-caret" />
    </button>

    <Teleport to="body">
      <Transition name="sd-drop">
        <ul
          v-if="open"
          ref="menuRef"
          class="sd-menu"
          :style="menuStyle"
          role="listbox"
          :aria-label="ariaLabel"
        >
          <li v-for="opt in options" :key="opt.value" role="option" :aria-selected="opt.value === modelValue">
            <button
              type="button"
              class="sd-option"
              :class="{ active: opt.value === modelValue }"
              @click="choose(opt)"
            >{{ opt.label }}</button>
          </li>
        </ul>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.sd {
  position: relative;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
}

.sd-btn {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  box-sizing: border-box;
  max-width: 100%;
  border: 1px solid var(--float-bg);
  background: var(--card-color);
  color: var(--text-color);
  font: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.sd-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.sd-btn:hover:not(:disabled),
.sd-btn.open {
  border-color: var(--notice-color);
}

.sd-value {
  overflow: hidden;
  text-overflow: ellipsis;
}

.sd-caret {
  flex-shrink: 0;
  color: var(--links-color);
  transition: transform 0.2s ease;
}

.sd-btn.open .sd-caret {
  transform: rotate(180deg);
}

/* pill：与反馈中心搜索框一致的胶囊样式（工具栏筛选） */
.sd-pill .sd-btn {
  height: 42px;
  padding: 0 18px;
  border-radius: 999px;
  font-size: 13.5px;
}

/* chip：表格内的状态标签 */
.sd-chip .sd-btn {
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12.5px;
  gap: 6px;
}

.sd-chip .sd-btn.is-pending {
  color: #d99a1f;
  border-color: rgba(235, 170, 40, 0.45);
}

.sd-chip .sd-btn.is-resolved {
  color: #2e9e5b;
  border-color: rgba(46, 158, 91, 0.45);
}

.sd-chip .sd-btn.is-closed {
  color: var(--links-color);
}

/* action：详情页操作按钮样式（与编辑/删除按钮一致） */
.sd-action .sd-btn {
  height: 38px;
  padding: 0 14px;
  border-radius: 10px;
  font-size: 13px;
}

.sd-action .sd-btn:hover:not(:disabled) {
  background: var(--float-bg);
}

/* 下拉菜单：fixed 定位 + 视口内约束，避免被 overflow 裁剪 / 超出屏幕 */
.sd-menu {
  position: fixed;
  z-index: 12000;
  box-sizing: border-box;
  max-width: calc(100vw - 16px);
  max-height: 44vh;
  overflow-y: auto;
  margin: 0;
  padding: 6px;
  list-style: none;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: var(--navbar-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.25);
}

.sd-option {
  display: block;
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 13.5px;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.sd-option:hover {
  background: var(--float-bg);
}

.sd-option.active {
  color: #d99a1f;
  font-weight: 700;
}

.sd-drop-enter-active,
.sd-drop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.sd-drop-enter-from,
.sd-drop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 768px) {
  /* 手机端：工具栏胶囊筛选与搜索框同宽 */
  .sd-pill {
    width: 100%;
  }

  .sd-pill .sd-btn {
    width: 100%;
  }
}
</style>

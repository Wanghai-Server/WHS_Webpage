<script setup>
/**
 * 目录树节点（递归组件）：按 h1–h6 层级嵌套渲染目录树。
 *
 * - 每层嵌套 <ul> 形成天然缩进（层层递进）；
 * - 子层绘制树状连接线（竖直引导线 + 到条目的水平短横），
 *   最后一个子节点的引导线只画到标题处（经典文件树风格）；
 * - 根节点（h1，页面标题）加粗突出；层级越深字号越小。
 */
import { computed } from 'vue'
// 显式自引用（递归渲染子层）。
// 注意：不能依赖"按文件名隐式自引用"——运行时 resolveComponent 的
// selfName 回退只看 displayName/name（不看 __name），小写文件名永远匹配不上。
import WikiOutlineNode from './wiki_outline_node.vue'

const props = defineProps({
  node: { type: Object, required: true },
  activeId: { type: String, default: '' },
  depth: { type: Number, default: 0 },
})

const emit = defineEmits(['select'])

const hasChildren = computed(() => !!props.node.children && props.node.children.length > 0)

function select() {
  emit('select', props.node)
}

// 子节点选中事件逐层上抛
function forward(event) {
  emit('select', event)
}
</script>

<template>
  <li class="toc-node" :class="{ 'has-children': hasChildren }">
    <button
      type="button"
      class="toc-item"
      :class="{
        active: node.id === activeId,
        'toc-root': node.level === 1,
      }"
      :style="{ '--toc-depth': depth }"
      :title="node.text"
      @click="select"
    >
      <span class="toc-text">{{ node.text }}</span>
    </button>
    <ul v-if="hasChildren" class="toc-children">
      <WikiOutlineNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :active-id="activeId"
        :depth="depth + 1"
        @select="forward"
      />
    </ul>
  </li>
</template>

<style scoped>
.toc-node {
  position: relative;
}

/* 目录条目 */
.toc-item {
  display: block;
  position: relative;
  width: 100%;
  box-sizing: border-box;
  margin: 1px 0;
  padding: 3px 8px;
  border: none;
  border-left: 2px solid transparent;
  border-radius: 0 6px 6px 0;
  background: transparent;
  color: var(--links-color);
  /* 层级越深字号越小（13px → 12.5px → 12px → 11.5px 封底） */
  font-size: max(11.5px, calc(13px - var(--toc-depth) * 0.5px));
  line-height: 1.45;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.toc-item:hover {
  background: var(--float-bg);
  color: var(--text-color);
}

.toc-item.active {
  border-left-color: var(--notice-color);
  background: var(--float-bg);
  color: var(--text-color);
  font-weight: 600;
}

/* 根节点：h1（页面标题）加粗突出 */
.toc-root {
  margin-bottom: 3px;
  padding-top: 5px;
  padding-bottom: 5px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-color);
}

.toc-root.active {
  border-left-color: var(--notice-color);
}

/* ---------- 子层：缩进 + 树状连接线 ---------- */
.toc-children {
  list-style: none;
  margin: 0;
  padding: 0 0 0 16px; /* 每层缩进，形成层层递进 */
}

/* 竖直引导线：画在每个节点的左侧（最后一个节点的线只画到标题处） */
.toc-children > .toc-node::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--float-bg);
}

.toc-children > .toc-node:last-child::before {
  bottom: 50%;
}

/* 水平短横：把引导线连接到条目文本（只画在子层，根层不画） */
.toc-children > .toc-node > .toc-item::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 50%;
  width: 12px;
  height: 1px;
  background: var(--float-bg);
}
</style>

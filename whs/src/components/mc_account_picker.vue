<script setup>
/**
 * 工程账号选择器：主账号 + 小号。
 *
 * - 仅在账号数 > 1 时由父组件渲染；
 * - "下次保持当前选择"把当前账号写入 localStorage（不落库）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTips } from '../composables/useTips'
import { rememberPlayer } from '../composables/useProjectPlayer'

const props = defineProps({
  accounts: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()
const { showTip } = useTips()

const selected = computed(() => props.modelValue || props.accounts[0]?.name || '')

function pick(name) {
  emit('update:modelValue', name)
}

function remember() {
  if (!selected.value) return
  rememberPlayer(selected.value)
  showTip('info', t('projects.accountRemembered'))
}
</script>

<template>
  <div class="account-picker">
    <span class="picker-label">{{ t('projects.selectAccount') }}</span>
    <div class="picker-options" role="radiogroup" :aria-label="t('projects.selectAccount')">
      <button
        v-for="account in accounts"
        :key="account.name"
        type="button"
        class="picker-option"
        :class="{ active: selected === account.name }"
        role="radio"
        :aria-checked="selected === account.name"
        @click="pick(account.name)"
      >
        <span class="picker-name">{{ account.name }}</span>
        <span v-if="account.primary" class="picker-badge">{{ t('projects.primaryAccount') }}</span>
      </button>
    </div>
    <button type="button" class="picker-remember" @click="remember">
      {{ t('projects.rememberAccount') }}
    </button>
  </div>
</template>

<style scoped>
.account-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.picker-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--links-color);
}

.picker-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.picker-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 999px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease, color 0.15s ease;
}

.picker-option:hover {
  background: var(--float-bg);
}

.picker-option.active {
  border-color: transparent;
  background: #ebaa28;
  color: #1f2937;
}

.picker-name {
  white-space: nowrap;
}

.picker-badge {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(31, 41, 55, 0.12);
  font-size: 11px;
  font-weight: 600;
}

.picker-option.active .picker-badge {
  background: rgba(31, 41, 55, 0.18);
}

.picker-remember {
  align-self: flex-start;
  padding: 4px 0;
  border: none;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 12px;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.picker-remember:hover {
  color: var(--text-color);
}
</style>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RefreshCw } from 'lucide-vue-next'
import { useTips } from '../composables/useTips'

const props = defineProps({
  base: { type: String, required: true },
})
const emit = defineEmits(['confirm', 'back'])

const { t } = useI18n()
const { showTip } = useTips()

const suggested = ref('')
const loading = ref(false)

async function fetchSuggestion() {
  loading.value = true
  try {
    const res = await fetch('/api/user/suggest_username', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base: props.base }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok && data.username) {
      suggested.value = data.username
    } else {
      showTip('error', t('auth.request_failed'))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchSuggestion)
</script>

<template>
  <div class="username-suggestion">
    <h1 class="title">{{ t('register.username_taken') }}</h1>
    <p class="hint">{{ t('register.suggest_hint') }}</p>

    <div class="suggestion-row">
      <span class="suggested">{{ suggested || '…' }}</span>
      <button
        type="button"
        class="refresh"
        :disabled="loading"
        :aria-label="t('register.refresh')"
        :title="t('register.refresh')"
        @click="fetchSuggestion"
      >
        <RefreshCw :size="18" />
      </button>
    </div>

    <div class="actions">
      <button type="button" class="btn back" @click="emit('back')">{{ t('register.back') }}</button>
      <button type="button" class="btn confirm" :disabled="!suggested" @click="emit('confirm', suggested)">
        {{ t('register.confirm') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-color);
  text-align: center;
}

.hint {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--links-color);
  text-align: center;
}

.suggestion-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.suggested {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  box-sizing: border-box;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  color: var(--text-color);
  font-size: 16px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.refresh {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  transition: color 0.2s ease;
}

.refresh:hover {
  color: var(--text-color);
}

.refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.actions {
  display: flex;
  gap: 10px;
}

.btn {
  flex: 1;
  padding: 12px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.btn.back {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn.confirm {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

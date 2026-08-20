<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Trash2, Pencil, X } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

// 「管理游戏账户」板块（用户设置-基本资料下）：
// - 非正式成员（permission < 2）：只展示"→成为我们的正式成员"按钮；
// - 正式成员：展示主账号（player_name + 主账号徽章 + 正版标签，可改正版状态）
//   与小号列表（可添加/注销，最多两个，正版标签在创建时选择）。
const props = defineProps({
  user: { type: Object, required: true }, // { uid, permission, ... }
})

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()

const isMember = computed(() => (props.user.permission ?? 0) >= 2)

// 账户数据：{player_name, premium, alts:[{name,premium}], max_alts}
const accounts = ref(null)
const loading = ref(false)
const busy = ref(false)

// 弹窗状态
const showAddAlt = ref(false)
const showPremiumDialog = ref(false)
const newAltName = ref('')
const newAltPremium = ref('')
const mainPremiumInput = ref('')
// 注销小号二次确认：记录待确认的小号名
const confirmAlt = ref('')
let confirmTimer = null

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

function authHeaders(extra = {}) {
  return {
    ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
    ...extra,
  }
}

function premiumLabel(flag) {
  if (flag === 'premium') return t('settings.premiumYes')
  if (flag === 'offline') return t('settings.premiumNo')
  return ''
}

function goExam() {
  router.push('/joinus/exam')
}

async function fetchAccounts() {
  loading.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/accounts`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      accounts.value = data
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (isMember.value) fetchAccounts()
})
watch(
  () => props.user.uid,
  () => {
    if (isMember.value) fetchAccounts()
  }
)

// 添加小号
async function addAlt() {
  const name = newAltName.value.trim()
  if (!/^[a-zA-Z0-9_]+$/.test(name)) {
    showTip('error', t('auth.username_invalid'))
    return
  }
  if (newAltPremium.value !== 'premium' && newAltPremium.value !== 'offline') {
    showTip('warning', t('settings.premiumLabel'))
    return
  }
  busy.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/alts`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ name, premium: newAltPremium.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.altAdded'))
      showAddAlt.value = false
      newAltName.value = ''
      newAltPremium.value = ''
      await fetchAccounts()
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    busy.value = false
  }
}

// 注销小号（二次确认）
function removeAlt(name) {
  if (confirmAlt.value !== name) {
    confirmAlt.value = name
    clearTimeout(confirmTimer)
    confirmTimer = setTimeout(() => {
      if (confirmAlt.value === name) confirmAlt.value = ''
    }, 2500)
    return
  }
  clearTimeout(confirmTimer)
  confirmAlt.value = ''
  busy.value = true
  ;(async () => {
    try {
      const res = await fetch(`/api/user/${props.user.uid}/alts/${encodeURIComponent(name)}`, {
        method: 'DELETE',
        headers: authHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        showTip('info', t('settings.altRemoved'))
        await fetchAccounts()
      } else {
        showTip('error', localMessage(data))
      }
    } catch (e) {
      showTip('error', t('auth.request_failed'))
      console.warn(e)
    } finally {
      busy.value = false
    }
  })()
}

// 修改主账号正版状态
async function saveMainPremium() {
  if (mainPremiumInput.value !== 'premium' && mainPremiumInput.value !== 'offline') return
  busy.value = true
  try {
    const res = await fetch(`/api/user/${props.user.uid}/premium`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ premium: mainPremiumInput.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('settings.premiumUpdated'))
      showPremiumDialog.value = false
      await fetchAccounts()
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="settings-card load-in" style="--load-delay: 120ms">
    <h2 class="card-title">{{ t('settings.manageAccounts') }}</h2>

    <!-- 非正式成员：引导参加入服考试 -->
    <button v-if="!isMember" type="button" class="btn primary" @click="goExam">
      {{ t('settings.becomeMember') }}
    </button>

    <!-- 正式成员：主账号 + 小号 -->
    <template v-else>
      <div v-if="loading" class="placeholder"><span class="spinner"></span>{{ t('admin.loading') }}</div>
      <template v-else-if="accounts">
        <!-- 主账号 -->
        <div class="account-row">
          <span class="account-name">{{ accounts.player_name || '—' }}</span>
          <span class="account-badge main">{{ t('settings.mainAccount') }}</span>
          <span v-if="premiumLabel(accounts.premium)" class="account-badge premium" :class="accounts.premium">
            {{ premiumLabel(accounts.premium) }}
          </span>
          <button
            type="button"
            class="btn modify"
            :disabled="busy"
            @click="mainPremiumInput = accounts.premium; showPremiumDialog = true"
          >
            <Pencil :size="16" />
            <span>{{ t('settings.changePremium') }}</span>
          </button>
        </div>

        <!-- 小号 -->
        <div class="alts-section">
          <div class="alts-head">
            <span class="alts-title">{{ t('settings.alts') }}</span>
            <button
              type="button"
              class="btn modify"
              :disabled="busy || accounts.alts.length >= accounts.max_alts"
              :title="accounts.alts.length >= accounts.max_alts ? t('settings.altMaxReached') : ''"
              @click="showAddAlt = true"
            >
              <Plus :size="16" />
              <span>{{ t('settings.addAlt') }}</span>
            </button>
          </div>
          <p v-if="accounts.alts.length >= accounts.max_alts" class="alt-hint">{{ t('settings.altMaxReached') }}</p>
          <p v-if="accounts.alts.length === 0" class="alts-empty">{{ t('settings.noAlts') }}</p>
          <div v-for="alt in accounts.alts" :key="alt.name" class="account-row">
            <span class="account-name">{{ alt.name }}</span>
            <span class="account-badge premium" :class="alt.premium">{{ premiumLabel(alt.premium) }}</span>
            <button type="button" class="btn modify danger" :disabled="busy" @click="removeAlt(alt.name)">
              <Trash2 :size="16" />
              <span>{{ confirmAlt === alt.name ? t('settings.confirmRemoveAlt') : t('settings.removeAlt') }}</span>
            </button>
          </div>
        </div>
      </template>
    </template>

    <!-- 添加小号弹窗 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showAddAlt" class="dialog-overlay" @click.self="showAddAlt = false">
          <div class="dialog-panel dialog">
            <header class="dialog-head">
              <h3>{{ t('settings.addAlt') }}</h3>
              <button type="button" class="dialog-close" :aria-label="t('message.close')" @click="showAddAlt = false">
                <X :size="18" />
              </button>
            </header>
            <div class="dialog-body">
              <div class="field">
                <label class="label">{{ t('settings.altName') }}</label>
                <input v-model="newAltName" type="text" :placeholder="t('settings.altNamePlaceholder')" />
              </div>
              <div class="field">
                <label class="label">{{ t('settings.premiumLabel') }}</label>
                <div class="premium-options">
                  <label class="premium-option">
                    <input v-model="newAltPremium" type="radio" value="premium" />
                    <span>{{ t('settings.premiumYes') }}</span>
                  </label>
                  <label class="premium-option">
                    <input v-model="newAltPremium" type="radio" value="offline" />
                    <span>{{ t('settings.premiumNo') }}</span>
                  </label>
                </div>
              </div>
              <div class="dialog-actions">
                <button type="button" class="btn cancel" @click="showAddAlt = false">{{ t('message.close') }}</button>
                <button type="button" class="btn primary" :disabled="busy" @click="addAlt">
                  {{ t('settings.addAlt') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 修改主账号正版状态弹窗 -->
    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showPremiumDialog" class="dialog-overlay" @click.self="showPremiumDialog = false">
          <div class="dialog-panel dialog">
            <header class="dialog-head">
              <h3>{{ t('settings.changePremium') }}</h3>
              <button type="button" class="dialog-close" :aria-label="t('message.close')" @click="showPremiumDialog = false">
                <X :size="18" />
              </button>
            </header>
            <div class="dialog-body">
              <div class="field">
                <label class="label">{{ t('settings.premiumLabel') }}</label>
                <div class="premium-options">
                  <label class="premium-option">
                    <input v-model="mainPremiumInput" type="radio" value="premium" />
                    <span>{{ t('settings.premiumYes') }}</span>
                  </label>
                  <label class="premium-option">
                    <input v-model="mainPremiumInput" type="radio" value="offline" />
                    <span>{{ t('settings.premiumNo') }}</span>
                  </label>
                </div>
              </div>
              <div class="dialog-actions">
                <button type="button" class="btn cancel" @click="showPremiumDialog = false">{{ t('message.close') }}</button>
                <button type="button" class="btn primary" :disabled="busy" @click="saveMainPremium">
                  {{ t('settings.confirmChange') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* 与 user_settings.vue 的 settings-card 同款（scoped 不跨组件，自包含一份） */
.settings-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border-radius: 20px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

.card-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.placeholder {
  padding: 24px 0;
  text-align: center;
  color: var(--links-color);
}

/* 账号行 */
.account-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.account-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-color);
  word-break: break-all;
}

.account-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.account-badge.main {
  background: rgba(235, 170, 40, 0.16);
  color: #ebaa28;
}

.account-badge.premium.premium {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.account-badge.premium.offline {
  background: rgba(148, 163, 184, 0.18);
  color: var(--links-color);
}

/* 小号区 */
.alts-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.alts-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.alts-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-color);
}

.alt-hint,
.alts-empty {
  margin: 0;
  font-size: 12.5px;
  color: var(--links-color);
}

/* 按钮（与 user_settings 同款） */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition:
    opacity 0.2s ease,
    background-color 0.2s ease,
    border-color 0.2s ease;
}

.btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.btn.modify {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn.modify:hover {
  background: var(--btn-hover);
}

.btn.modify.danger {
  border-color: rgba(229, 72, 77, 0.45);
  color: #e5484d;
}

.btn.modify.danger:hover {
  background: rgba(229, 72, 77, 0.1);
}

.btn.cancel {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 弹窗（与全站毛玻璃惯例一致：遮罩半透明+轻模糊，面板 navbar 半透明底+12px 模糊） */
.dialog-overlay {
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

.dialog-panel {
  width: min(420px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: var(--navbar-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 20px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.3);
}

.dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.dialog-head h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-color);
}

.dialog-close {
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

.dialog-close:hover {
  background: var(--btn-hover);
  color: var(--text-color);
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.label {
  font-size: 14px;
  color: var(--links-color);
}

.field input[type='text'] {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
  font: inherit;
  outline: none;
  transition: border-color 0.2s ease;
}

.field input[type='text']:focus {
  border-color: var(--text-color);
}

.premium-options {
  display: flex;
  gap: 10px;
}

.premium-option {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  color: var(--text-color);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.premium-option:has(input:checked) {
  border-color: rgba(235, 170, 40, 0.6);
  background: rgba(235, 170, 40, 0.1);
}

.premium-option input {
  accent-color: #ebaa28;
}
</style>

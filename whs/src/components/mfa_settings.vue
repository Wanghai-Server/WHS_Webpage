<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShieldCheck, Smartphone } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { copyText } from '../composables/clipboard'

const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

const status = ref({
  totp_enabled: false,
  ms_enabled: false,
  ms_email: '',
  ms_available: false,
  recovery_remaining: 0,
})

// 当前弹窗：'' | 'totp-setup' | 'recovery' | 'disable' | 'ms-bind' | 'regen'
const dialog = ref('')
const loading = ref(false)

// 验证器 App 设置
const setupData = ref({ secret: '', otpauth_uri: '', qr_svg: '' })
const code = ref('')
const submitting = ref(false)

// 恢复码
const recoveryCodes = ref([])

// 关闭 / 重新生成时的凭证
const proofKind = ref('totp') // 'totp' | 'microsoft'
const proofMode = ref('totp') // 'totp' | 'recovery'
const proofCode = ref('')

// 微软账号批准
const msDevice = ref(null)
const msWaiting = ref(false)
const msRemaining = ref(0)
let msPollTimer = null
let msCountdownTimer = null

const msCountdownText = computed(() => {
  const total = Math.max(0, msRemaining.value)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
})

function headers(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
    ...extra,
  }
}

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function request(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(localMessage(data))
  return data
}

async function fetchStatus() {
  if (!authState.token) return
  loading.value = true
  try {
    status.value = await request('/api/user/mfa')
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchStatus)

// ---------------------------------------------------------------------------
// 验证器 App（TOTP）
// ---------------------------------------------------------------------------
async function openTotpSetup() {
  if (submitting.value) return
  submitting.value = true
  try {
    setupData.value = await request('/api/user/mfa/totp/setup', {})
    code.value = ''
    dialog.value = 'totp-setup'
  } catch (e) {
    showTip('error', e.message)
  } finally {
    submitting.value = false
  }
}

async function confirmTotp() {
  if (!/^\d{6}$/.test(code.value.trim())) {
    showTip('warning', t('settings.mfa.code_hint'))
    return
  }
  submitting.value = true
  try {
    const data = await request('/api/user/mfa/totp/enable', { code: code.value.trim() })
    recoveryCodes.value = data.recovery_codes || []
    // 重复提交时后端返回成功但不再重复发放恢复码：直接关闭弹窗即可
    dialog.value = recoveryCodes.value.length ? 'recovery' : ''
    await fetchStatus()
    showTip('info', t('settings.mfa.enabled_tip'))
  } catch (e) {
    showTip('error', e.message)
  } finally {
    submitting.value = false
  }
}

// ---------------------------------------------------------------------------
// 恢复码
// ---------------------------------------------------------------------------
async function copyCodes() {
  const ok = await copyText(recoveryCodes.value.join('\n'))
  showTip(ok ? 'info' : 'warning', t(ok ? 'settings.mfa.copied' : 'auth.mfa_copy_failed'))
}

async function copySecret() {
  const ok = await copyText(setupData.value.secret)
  showTip(ok ? 'info' : 'warning', t(ok ? 'settings.mfa.copied' : 'auth.mfa_copy_failed'))
}

// ---------------------------------------------------------------------------
// 微软账号批准（设备码流程）
// ---------------------------------------------------------------------------
function stopMsTimers() {
  if (msPollTimer) {
    clearInterval(msPollTimer)
    msPollTimer = null
  }
  if (msCountdownTimer) {
    clearInterval(msCountdownTimer)
    msCountdownTimer = null
  }
  msWaiting.value = false
}

async function startMsBind() {
  if (submitting.value || msWaiting.value) return
  submitting.value = true
  try {
    const data = await request('/api/user/mfa/ms/bind/start', {})
    msDevice.value = data
    msRemaining.value = Number(data.expires_in) || 900
    beginPolling(Number(data.interval) || 5)
  } catch (e) {
    showTip('error', e.message)
  } finally {
    submitting.value = false
  }
}

let polling = false

async function pollOnce() {
  if (!msDevice.value || !msWaiting.value || polling) return
  polling = true
  try {
    const data = await request('/api/user/mfa/ms/bind/poll', {
      challenge_id: msDevice.value.challenge_id,
    })
    if (data.status === 'success') {
      stopMsTimers()
      msDevice.value = null
      await fetchStatus()
      if (data.recovery_codes && data.recovery_codes.length) {
        recoveryCodes.value = data.recovery_codes
        dialog.value = 'recovery'
      } else {
        dialog.value = ''
      }
      showTip('info', t('settings.mfa.ms_bound'))
      return
    }
    if (data.status === 'slow_down') {
      beginPolling(Number(msDevice.value.interval || 5) + 5)
      return
    }
    if (['declined', 'expired', 'error'].includes(data.status)) {
      stopMsTimers()
      msDevice.value = null
      showTip('error', t(data.status === 'declined' ? 'auth.mfa_ms_declined' : 'auth.mfa_ms_expired'))
    }
  } catch (e) {
    showTip('error', e.message)
    stopMsTimers()
  } finally {
    polling = false
  }
}

function beginPolling(seconds) {
  stopMsTimers()
  msWaiting.value = true
  msPollTimer = setInterval(pollOnce, Math.max(5, seconds) * 1000)
  msCountdownTimer = setInterval(() => {
    msRemaining.value -= 1
    if (msRemaining.value <= 0) {
      stopMsTimers()
      msDevice.value = null
      showTip('error', t('auth.mfa_ms_expired'))
    }
  }, 1000)
  pollOnce()
}

function openDevicePage() {
  if (msDevice.value?.verification_uri) {
    window.open(msDevice.value.verification_uri, '_blank', 'noopener')
  }
}

function openMsBind() {
  msDevice.value = null
  stopMsTimers()
  dialog.value = 'ms-bind'
}

// ---------------------------------------------------------------------------
// 关闭 / 重新生成
// ---------------------------------------------------------------------------
function openDisable(kind) {
  proofKind.value = kind
  proofMode.value = 'totp'
  proofCode.value = ''
  dialog.value = 'disable'
}

async function submitDisable() {
  const body = { code: proofCode.value.trim(), mode: proofMode.value }
  submitting.value = true
  try {
    const path =
      proofKind.value === 'microsoft' ? '/api/user/mfa/ms/disable' : '/api/user/mfa/totp/disable'
    await request(path, body)
    dialog.value = ''
    proofCode.value = ''
    await fetchStatus()
    showTip('info', t('settings.mfa.disabled_tip'))
  } catch (e) {
    showTip('error', e.message)
  } finally {
    submitting.value = false
  }
}

function openRegen() {
  proofMode.value = 'totp'
  proofCode.value = ''
  dialog.value = 'regen'
}

async function submitRegen() {
  if (!proofCode.value.trim()) {
    showTip('warning', t('settings.mfa.code_required'))
    return
  }
  submitting.value = true
  try {
    const data = await request('/api/user/mfa/recovery/regenerate', {
      code: proofCode.value.trim(),
      mode: proofMode.value,
    })
    recoveryCodes.value = data.recovery_codes || []
    dialog.value = 'recovery'
    await fetchStatus()
  } catch (e) {
    showTip('error', e.message)
  } finally {
    submitting.value = false
  }
}

function closeDialog() {
  stopMsTimers()
  msDevice.value = null
  dialog.value = ''
  code.value = ''
  proofCode.value = ''
}

onUnmounted(stopMsTimers)
</script>

<template>
  <div class="settings-card load-in" style="--load-delay: 340ms">
    <h3 class="card-title">{{ t('settings.mfa.title') }}</h3>
    <p class="mfa-desc">{{ t('settings.mfa.subtitle') }}</p>

    <!-- 验证器 App -->
    <div class="setting-row">
      <div class="mfa-meta">
        <span class="row-title">
          <Smartphone :size="16" />
          {{ t('settings.mfa.totp') }}
        </span>
        <span class="mfa-desc">{{ t('settings.mfa.totp_desc') }}</span>
      </div>
      <div class="mfa-side">
        <span class="mfa-badge" :class="{ on: status.totp_enabled }">
          {{ status.totp_enabled ? t('settings.mfa.on') : t('settings.mfa.off') }}
        </span>
        <button
          class="btn modify"
          :class="{ danger: status.totp_enabled }"
          :disabled="loading"
          @click="status.totp_enabled ? openDisable('totp') : openTotpSetup()"
        >
          {{ status.totp_enabled ? t('settings.mfa.disable') : t('settings.mfa.enable') }}
        </button>
      </div>
    </div>

    <!-- 微软账号批准 -->
    <div class="setting-row">
      <div class="mfa-meta">
        <span class="row-title">
          <ShieldCheck :size="16" />
          {{ t('settings.mfa.microsoft') }}
        </span>
        <span class="mfa-desc">
          {{ status.ms_enabled ? status.ms_email : t('settings.mfa.microsoft_desc') }}
        </span>
      </div>
      <div class="mfa-side">
        <span v-if="!status.ms_available" class="mfa-badge muted">
          {{ t('settings.mfa.unconfigured') }}
        </span>
        <span v-else class="mfa-badge" :class="{ on: status.ms_enabled }">
          {{ status.ms_enabled ? t('settings.mfa.on') : t('settings.mfa.off') }}
        </span>
        <button
          class="btn modify"
          :class="{ danger: status.ms_enabled }"
          :disabled="loading || (!status.ms_available && !status.ms_enabled)"
          @click="status.ms_enabled ? openDisable('microsoft') : openMsBind()"
        >
          {{ status.ms_enabled ? t('settings.mfa.unbind') : t('settings.mfa.bind') }}
        </button>
      </div>
    </div>

    <!-- 恢复码状态 -->
    <div v-if="status.totp_enabled || status.ms_enabled" class="mfa-foot">
      <span class="mfa-desc">
        {{ t('settings.mfa.recovery_left', { n: status.recovery_remaining }) }}
      </span>
      <button class="link-btn" @click="openRegen">{{ t('settings.mfa.regen') }}</button>
    </div>

    <!-- 管理员配置提示：置于卡片底部，普通用户可忽略 -->
    <p v-if="!status.ms_available" class="mfa-config">
      {{ t('settings.mfa.config_hint') }}
    </p>

    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="dialog" class="dialog-overlay" @click.self="closeDialog">
          <div class="dialog">
            <!-- 1. 绑定验证器 App -->
            <template v-if="dialog === 'totp-setup'">
              <h3 class="dialog-title">{{ t('settings.mfa.setup_title') }}</h3>
              <p class="mfa-desc">{{ t('settings.mfa.scan_hint') }}</p>
              <div v-if="setupData.qr_svg" class="qr-box" v-html="setupData.qr_svg"></div>
              <div class="secret-row">
                <code>{{ setupData.secret }}</code>
                <button class="link-btn" @click="copySecret">{{ t('settings.mfa.copy') }}</button>
              </div>
              <p class="mfa-desc">
                <a class="link-btn" :href="setupData.otpauth_uri">{{ t('settings.mfa.open_app') }}</a>
              </p>
              <p class="mfa-desc">{{ t('settings.mfa.manual_hint') }}</p>
              <label class="float-field">
                <input
                  v-model="code"
                  type="text"
                  inputmode="numeric"
                  maxlength="6"
                  autocomplete="one-time-code"
                  placeholder=" "
                />
                <span class="float-label">{{ t('settings.mfa.code') }}</span>
              </label>
              <div class="dialog-actions">
                <button class="btn cancel" @click="closeDialog">{{ t('admin.cancel') }}</button>
                <button class="btn primary" :disabled="submitting" @click="confirmTotp">
                  <span v-if="submitting" class="spinner"></span>
                  {{ t('settings.mfa.confirm_enable') }}
                </button>
              </div>
            </template>

            <!-- 2. 恢复码展示 -->
            <template v-else-if="dialog === 'recovery'">
              <h3 class="dialog-title">{{ t('settings.mfa.codes_title') }}</h3>
              <p class="mfa-desc">{{ t('settings.mfa.codes_hint') }}</p>
              <div class="recovery-grid">
                <code v-for="item in recoveryCodes" :key="item">{{ item }}</code>
              </div>
              <div class="dialog-actions">
                <button class="btn ghost" @click="copyCodes">{{ t('settings.mfa.copy_all') }}</button>
                <button class="btn primary" @click="closeDialog">{{ t('settings.mfa.saved') }}</button>
              </div>
            </template>

            <!-- 3. 关闭验证方式 -->
            <template v-else-if="dialog === 'disable'">
              <h3 class="dialog-title">
                {{ t('settings.mfa.disable_title', { name: proofKind === 'microsoft' ? t('settings.mfa.microsoft') : t('settings.mfa.totp') }) }}
              </h3>
              <div v-if="status.totp_enabled" class="mfa-tabs">
                <button :class="{ active: proofMode === 'totp' }" @click="proofMode = 'totp'; proofCode = ''">
                  {{ t('settings.mfa.code') }}
                </button>
                <button :class="{ active: proofMode === 'recovery' }" @click="proofMode = 'recovery'; proofCode = ''">
                  {{ t('settings.mfa.recovery') }}
                </button>
              </div>
              <label v-if="status.totp_enabled" class="float-field">
                <input v-model="proofCode" type="text" autocomplete="off" placeholder=" " />
                <span class="float-label">
                  {{ proofMode === 'recovery' ? t('settings.mfa.recovery') : t('settings.mfa.code') }}
                </span>
              </label>
              <p v-else class="mfa-desc">{{ t('settings.mfa.disable_ms_hint') }}</p>
              <div class="dialog-actions">
                <button class="btn cancel" @click="closeDialog">{{ t('admin.cancel') }}</button>
                <button class="btn primary danger-fill" :disabled="submitting" @click="submitDisable">
                  <span v-if="submitting" class="spinner"></span>
                  {{ t('settings.mfa.confirm_disable') }}
                </button>
              </div>
            </template>

            <!-- 4. 重新生成恢复码 -->
            <template v-else-if="dialog === 'regen'">
              <h3 class="dialog-title">{{ t('settings.mfa.regen') }}</h3>
              <div class="mfa-tabs">
                <button :class="{ active: proofMode === 'totp' }" @click="proofMode = 'totp'; proofCode = ''">
                  {{ t('settings.mfa.code') }}
                </button>
                <button :class="{ active: proofMode === 'recovery' }" @click="proofMode = 'recovery'; proofCode = ''">
                  {{ t('settings.mfa.recovery') }}
                </button>
              </div>
              <label class="float-field">
                <input v-model="proofCode" type="text" autocomplete="off" placeholder=" " />
                <span class="float-label">
                  {{ proofMode === 'recovery' ? t('settings.mfa.recovery') : t('settings.mfa.code') }}
                </span>
              </label>
              <div class="dialog-actions">
                <button class="btn cancel" @click="closeDialog">{{ t('admin.cancel') }}</button>
                <button class="btn primary" :disabled="submitting" @click="submitRegen">
                  <span v-if="submitting" class="spinner"></span>
                  {{ t('settings.mfa.regenerate') }}
                </button>
              </div>
            </template>

            <!-- 5. 绑定微软账号 -->
            <template v-else-if="dialog === 'ms-bind'">
              <h3 class="dialog-title">{{ t('settings.mfa.bind_title') }}</h3>
              <ol class="ms-steps">
                <li>{{ t('settings.mfa.bind_step1') }}</li>
                <li>{{ t('settings.mfa.bind_step2') }}</li>
                <li>{{ t('settings.mfa.bind_step3') }}</li>
              </ol>
              <template v-if="!msDevice">
                <div class="dialog-actions">
                  <button class="btn cancel" @click="closeDialog">{{ t('admin.cancel') }}</button>
                  <button class="btn primary" :disabled="submitting" @click="startMsBind">
                    <span v-if="submitting" class="spinner"></span>
                    {{ t('settings.mfa.bind_start') }}
                  </button>
                </div>
              </template>
              <template v-else>
                <button class="device-code" @click="copyText(msDevice.user_code)">
                  {{ msDevice.user_code }}
                </button>
                <button class="btn ghost ms-open" @click="openDevicePage">
                  {{ t('auth.mfa_ms_open') }}
                </button>
                <p class="mfa-status">
                  <span v-if="msWaiting" class="spinner"></span>
                  <span>{{ msWaiting ? t('auth.mfa_ms_waiting') : '' }}</span>
                  <span v-if="msWaiting" class="mfa-countdown">{{ msCountdownText }}</span>
                </p>
                <div class="dialog-actions">
                  <button class="btn cancel" @click="closeDialog">{{ t('admin.cancel') }}</button>
                </div>
              </template>
            </template>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* 与 user_settings.vue 同款卡片/弹窗样式（scoped 不跨组件，自包含一份） */
.settings-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 24px 28px;
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

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.mfa-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.row-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}

.mfa-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--links-color);
  word-break: break-word;
}

.mfa-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.mfa-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  background: rgba(148, 163, 184, 0.16);
  color: var(--links-color);
}

.mfa-badge.on {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.mfa-badge.muted {
  background: rgba(235, 170, 40, 0.15);
  color: #ebaa28;
}

.mfa-config {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(235, 170, 40, 0.1);
  color: #ebaa28;
  font-size: 12px;
  line-height: 1.6;
}

.mfa-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.btn.primary {
  border: none;
  background: var(--text-color);
  color: var(--bg-color);
}

.btn.primary.danger-fill {
  background: #e5484d;
  color: #fff;
}

.btn.ghost {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--links-color);
}

.btn.modify {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: var(--text-color);
}

.btn.modify:hover {
  background: var(--float-bg);
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

.link-btn {
  border: none;
  background: none;
  padding: 0;
  color: var(--links-color);
  font: inherit;
  cursor: pointer;
  transition: color 0.2s ease;
}

.link-btn:hover {
  color: var(--text-color);
}

/* 二维码：固定白底，保证深浅色主题下都能被相机识别 */
.qr-box {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  margin: 4px auto;
  border-radius: 12px;
  background: #ffffff;
  width: fit-content;
}

.qr-box :deep(svg) {
  display: block;
  width: 200px;
  height: 200px;
}

.secret-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--float-bg);
}

.secret-row code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  letter-spacing: 0.08em;
  color: var(--text-color);
  word-break: break-all;
}

.recovery-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin: 8px 0;
}

.recovery-grid code {
  padding: 8px;
  border-radius: 8px;
  background: var(--float-bg);
  color: var(--text-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 14px;
  text-align: center;
  letter-spacing: 0.06em;
}

.mfa-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  padding: 4px;
  border-radius: 999px;
  background: var(--float-bg);
}

.mfa-tabs button {
  flex: 1;
  padding: 8px 4px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--links-color);
  font: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mfa-tabs button.active {
  background: var(--card-color);
  color: var(--text-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.ms-steps {
  margin: 0 0 14px;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--links-color);
}

.device-code {
  width: 100%;
  padding: 14px 12px;
  margin-bottom: 10px;
  border: 1px dashed rgba(148, 163, 184, 0.5);
  border-radius: 12px;
  background: var(--float-bg);
  color: var(--text-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-indent: 0.16em;
  cursor: pointer;
}

.ms-open {
  width: 100%;
  justify-content: center;
}

.mfa-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 12px 0;
  min-height: 20px;
  font-size: 13px;
  color: var(--links-color);
}

.mfa-countdown {
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}

/* 对话框（与 user_settings.vue 一致） */
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 9500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.dialog {
  --float-label-bg: var(--navbar-bg);
  width: min(420px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  padding: 24px;
  border-radius: 16px;
  background: var(--navbar-bg);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  color: var(--text-color);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dialog-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}
</style>

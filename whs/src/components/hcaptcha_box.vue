<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import VueHcaptcha from '@hcaptcha/vue3-hcaptcha'

// hCaptcha 官方控件的 iframe 内部固定为约 303×78，且跨域无法修改其内部布局。
// 这里的处理：容器够宽时按原始尺寸居中；容器更窄时整体等比缩放，避免被强制拉伸/裁切。
const BASE_WIDTH = 303
const BASE_HEIGHT = 78

defineProps({
  sitekey: { type: String, required: true },
  theme: { type: String, default: undefined },
})
const emit = defineEmits(['verify', 'expired', 'error'])

const wrap = ref(null)
const captcha = ref(null)
const scale = ref(1)
const contentHeight = ref(BASE_HEIGHT)
let observer = null

const boxHeight = computed(() => Math.max(1, contentHeight.value * scale.value))

function measure() {
  const width = wrap.value ? wrap.value.clientWidth : 0
  scale.value = width > 0 ? Math.min(1, width / BASE_WIDTH) : 1
  const el = captcha.value && captcha.value.$el
  if (el) {
    const height = el.getBoundingClientRect().height
    if (height > 0) contentHeight.value = height
  }
}

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => measure())
    if (wrap.value) observer.observe(wrap.value)
    if (captcha.value && captcha.value.$el) observer.observe(captcha.value.$el)
  }
  nextTick(measure)
})

onUnmounted(() => {
  if (observer) observer.disconnect()
})

function reset() {
  // 控件尚未渲染时调用 reset 会触发库的 error 事件（控制台噪音），这里先判空
  if (captcha.value && captcha.value.widgetId) captcha.value.reset()
}

defineExpose({ reset })
</script>

<template>
  <div ref="wrap" class="hcaptcha-box" :style="{ height: `${boxHeight}px` }">
    <div class="hcaptcha-scaler" :style="{ transform: `scale(${scale})` }">
      <VueHcaptcha
        ref="captcha"
        :sitekey="sitekey"
        :theme="theme"
        api-endpoint="https://js.hcaptcha.com/1/api.js"
        @verify="(token, eKey) => emit('verify', token, eKey)"
        @expired="() => emit('expired')"
        @error="(err) => emit('error', err)"
      />
    </div>
  </div>
</template>

<style scoped>
.hcaptcha-box {
  position: relative;
  width: 100%;
}

.hcaptcha-scaler {
  position: absolute;
  top: 0;
  left: 50%;
  width: 303px;
  margin-left: -151.5px;
  transform-origin: top center;
}
</style>

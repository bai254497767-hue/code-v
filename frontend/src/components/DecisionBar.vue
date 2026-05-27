<template>
  <div class="decision-bar">
    <div class="decision-info">
      <div class="decision-title">
        <span class="decision-emoji">{{ interrupt.emoji }}</span>
        <span class="decision-label">{{ interrupt.title }} — 请确认或输入修改意见</span>
        <span class="decision-countdown" :class="{ paused: countdownPaused }">
          {{ countdownText }}
        </span>
      </div>
      <textarea
        v-model="feedback"
        class="decision-input"
        rows="2"
        placeholder="输入意见后可重新生成当前阶段，例如：范围缩小到销售线索和库存管理，先不要做财务统计。"
        @input="pauseCountdown"
      ></textarea>
    </div>
    <div class="decision-buttons">
      <button
        class="btn-continue"
        @click="decideByContent"
      >
        {{ primaryButtonText }}
      </button>
      <button class="btn-abort" @click="decide('abort')">
        暂停
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useProjectStore } from '../stores/project.js'

const props = defineProps({ interrupt: Object })
const store = useProjectStore()
const AUTO_CONFIRM_SECONDS = 60
const feedback = ref('')
const secondsLeft = ref(AUTO_CONFIRM_SECONDS)
const countdownPaused = ref(false)
let timerId = null

const hasFeedback = computed(() => feedback.value.trim().length > 0)
const primaryButtonText = computed(() => hasFeedback.value ? '按意见重生成' : '确认继续')
const countdownText = computed(() => {
  if (countdownPaused.value) return '已暂停自动确认'
  return `${secondsLeft.value} 秒后自动确认`
})

watch(
  () => props.interrupt,
  () => {
    resetDecisionBar()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  stopCountdown()
})

function resetDecisionBar() {
  feedback.value = ''
  secondsLeft.value = AUTO_CONFIRM_SECONDS
  countdownPaused.value = false
  startCountdown()
}

function startCountdown() {
  stopCountdown()
  timerId = window.setInterval(() => {
    if (countdownPaused.value) return
    secondsLeft.value -= 1
    if (secondsLeft.value <= 0) {
      decide('continue')
    }
  }, 1000)
}

function stopCountdown() {
  if (timerId) {
    window.clearInterval(timerId)
    timerId = null
  }
}

function pauseCountdown() {
  if (!countdownPaused.value) {
    countdownPaused.value = true
    stopCountdown()
  }
}

function decideByContent() {
  decide(hasFeedback.value ? 'retry' : 'continue')
}

function decide(action) {
  stopCountdown()
  store.sendDecision(action, feedback.value.trim())
  if (action !== 'retry') {
    feedback.value = ''
  }
}
</script>

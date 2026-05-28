<template>
  <div class="chat-composer">
    <div v-if="store.feedbackQueue.length" class="feedback-queue">
      <div class="queue-title">待调度意见</div>
      <div v-for="item in store.feedbackQueue" :key="item.id" class="queue-item">
        {{ item.text }}
      </div>
    </div>

    <div v-if="store.pendingInterrupt" class="composer-waiting">
      <span>{{ store.pendingInterrupt.title }} 正在等待确认</span>
      <span class="decision-countdown" :class="{ paused: countdownPaused }">{{ countdownText }}</span>
    </div>

    <div v-if="store.pendingInterrupt" class="confirmation-popover">
      <div class="confirmation-popover-title">正在确认的内容</div>
      <div class="confirmation-popover-body">
        <StageCard
          :msg="confirmationMsg"
          :project-state="store.stateSnapshot"
        />
      </div>
    </div>

    <div class="composer-row">
      <textarea
        v-model="draft"
        class="composer-input"
        rows="2"
        placeholder="随时输入修改意见，例如：后端接口加搜索参数，或页面改成表格视图。"
        @input="pauseCountdown"
        @keydown.meta.enter.prevent="submit"
        @keydown.ctrl.enter.prevent="submit"
      ></textarea>
      <div class="composer-actions">
        <button class="btn-continue" type="button" @click="submit">
          {{ submitting ? '发送中...' : primaryText }}
        </button>
        <button class="btn-retry" type="button" @click="interrupt">
          打断交给 CEO
        </button>
        <button
          v-if="store.pendingInterrupt"
          class="btn-abort"
          type="button"
          @click="store.sendDecision('abort')"
        >
          暂停
        </button>
      </div>
    </div>
    <div v-if="error" class="composer-error">{{ error }}</div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useProjectStore } from '../stores/project.js'
import StageCard from './StageCard.vue'

const store = useProjectStore()
const AUTO_CONFIRM_SECONDS = 60
const draft = ref('')
const error = ref('')
const submitting = ref(false)
const secondsLeft = ref(AUTO_CONFIRM_SECONDS)
const countdownPaused = ref(false)
let timerId = null

const hasDraft = computed(() => draft.value.trim().length > 0)
const primaryText = computed(() => {
  if (hasDraft.value) return '发送给 CEO'
  if (store.pendingInterrupt) return '确认继续'
  return '发送'
})
const countdownText = computed(() => {
  if (countdownPaused.value) return '已暂停自动确认'
  return `${secondsLeft.value} 秒后自动确认`
})
const confirmationMsg = computed(() => {
  const intr = store.pendingInterrupt || {}
  return {
    id: `confirm-${intr.stage || 'stage'}`,
    stage: intr.stage,
    emoji: intr.emoji,
    title: intr.title,
    data: intr.data,
    extra: extractExtra(intr),
    status: 'waiting',
  }
})

watch(
  () => store.pendingInterrupt,
  () => resetTimer(),
  { immediate: true }
)
watch(
  () => store.feedbackQueue.length,
  () => resetTimer()
)

onBeforeUnmount(stopTimer)

function resetTimer() {
  stopTimer()
  secondsLeft.value = AUTO_CONFIRM_SECONDS
  countdownPaused.value = false
  if (store.pendingInterrupt && !hasDraft.value && store.feedbackQueue.length === 0) {
    timerId = window.setInterval(() => {
      if (countdownPaused.value) return
      secondsLeft.value -= 1
      if (secondsLeft.value <= 0) {
        stopTimer()
        store.sendDecision('continue')
      }
    }, 1000)
  }
}

function stopTimer() {
  if (timerId) {
    window.clearInterval(timerId)
    timerId = null
  }
}

function pauseCountdown() {
  if (!countdownPaused.value) {
    countdownPaused.value = true
    stopTimer()
  }
}

function extractExtra(msg) {
  const reserved = ['type', 'stage', 'emoji', 'title', 'data', 'task_context']
  const extra = {}
  for (const key of Object.keys(msg || {})) {
    if (!reserved.includes(key)) extra[key] = msg[key]
  }
  return extra
}

async function submit() {
  if (submitting.value) return
  error.value = ''
  const text = draft.value.trim()
  submitting.value = true
  try {
    if (text) {
      await store.submitChat(text)
      draft.value = ''
      resetTimer()
      return
    }
    if (store.pendingInterrupt) {
      await store.sendDecision('continue')
    }
  } catch (e) {
    error.value = e.message || '发送失败'
  } finally {
    submitting.value = false
  }
}

async function interrupt() {
  error.value = ''
  try {
    const text = draft.value.trim()
    await store.requestInterrupt(text)
    draft.value = ''
    pauseCountdown()
  } catch (e) {
    error.value = e.message || '请求打断失败'
  }
}
</script>

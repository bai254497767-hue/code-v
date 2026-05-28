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

    <div v-if="isQuestionInterrupt" class="question-popover">
      <div class="question-title">{{ store.pendingInterrupt.question }}</div>
      <div v-if="questionAllowsMultiple" class="question-mode-hint">
        可多选，第一项为 CEO 推荐优先项。
      </div>
      <div v-else class="question-mode-hint">
        单选，第一项为 CEO 推荐优先项。
      </div>
      <div v-if="store.pendingInterrupt.data?.reason" class="question-reason">
        {{ store.pendingInterrupt.data.reason }}
      </div>
      <div class="question-options">
        <button
          v-for="(option, index) in questionOptions"
          :key="option"
          type="button"
          class="question-option"
          :class="{ selected: selectedQuestionOptions.includes(option), recommended: index === 0 }"
          @click="questionAllowsMultiple ? toggleQuestionOption(option) : answerQuestion(option)"
        >
          <span v-if="questionAllowsMultiple" class="question-check">
            {{ selectedQuestionOptions.includes(option) ? '✓' : '+' }}
          </span>
          <span v-if="index === 0" class="question-recommended">推荐</span>
          {{ option }}
        </button>
      </div>
      <button
        v-if="questionAllowsMultiple"
        class="question-submit"
        type="button"
        :disabled="selectedQuestionOptions.length === 0 || submitting"
        @click="submitSelectedQuestionOptions"
      >
        提交已选 {{ selectedQuestionOptions.length }} 项
      </button>
      <div class="question-custom-hint">也可以在下方输入自定义答案后发送。</div>
    </div>

    <div v-else-if="store.pendingInterrupt" class="confirmation-popover">
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
        :placeholder="inputPlaceholder"
        @input="pauseCountdown"
        @keydown.meta.enter.prevent="submit"
        @keydown.ctrl.enter.prevent="submit"
      ></textarea>
      <div class="composer-actions">
        <button class="btn-continue" type="button" :disabled="isQuestionInterrupt && !hasDraft" @click="submit">
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
const selectedQuestionOptions = ref([])
let timerId = null

const hasDraft = computed(() => draft.value.trim().length > 0)
const isQuestionInterrupt = computed(() =>
  Boolean(store.pendingInterrupt?.allow_custom_input && store.pendingInterrupt?.question)
)
const questionAllowsMultiple = computed(() =>
  Boolean(store.pendingInterrupt?.allow_multiple || store.pendingInterrupt?.data?.allow_multiple)
)
const questionOptions = computed(() =>
  (store.pendingInterrupt?.options || store.pendingInterrupt?.data?.options || []).slice(0, 6)
)
const primaryText = computed(() => {
  if (isQuestionInterrupt.value) return hasDraft.value ? '提交自定义答案' : '选择或输入答案'
  if (hasDraft.value) return '发送给 CEO'
  if (store.pendingInterrupt) return '确认继续'
  return '发送'
})
const inputPlaceholder = computed(() => {
  if (isQuestionInterrupt.value) return '输入自定义答案，例如：优先服务中小车商内部 CRM 场景。'
  return '随时输入修改意见，例如：后端接口加搜索参数，或页面改成表格视图。'
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
  selectedQuestionOptions.value = []
  if (store.pendingInterrupt && !isQuestionInterrupt.value && !hasDraft.value && store.feedbackQueue.length === 0) {
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
      if (isQuestionInterrupt.value) {
        await store.answerQuestion(text, 'custom')
        draft.value = ''
        resetTimer()
        return
      }
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

async function answerQuestion(option) {
  if (submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    await store.answerQuestion(option, 'option')
    draft.value = ''
    resetTimer()
  } catch (e) {
    error.value = e.message || '提交答案失败'
  } finally {
    submitting.value = false
  }
}

function toggleQuestionOption(option) {
  pauseCountdown()
  selectedQuestionOptions.value = selectedQuestionOptions.value.includes(option)
    ? selectedQuestionOptions.value.filter(item => item !== option)
    : [...selectedQuestionOptions.value, option]
}

async function submitSelectedQuestionOptions() {
  if (submitting.value || selectedQuestionOptions.value.length === 0) return
  submitting.value = true
  error.value = ''
  try {
    const answer = selectedQuestionOptions.value.join('；')
    await store.answerQuestion(answer, 'multi_option', selectedQuestionOptions.value)
    draft.value = ''
    resetTimer()
  } catch (e) {
    error.value = e.message || '提交答案失败'
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

<template>
  <div class="chat-area">
    <!-- 空状态 -->
    <div v-if="!store.currentId" class="empty-state">
      <div class="empty-icon">AI</div>
      <div class="empty-title">AI 软件工厂</div>
      <div class="empty-desc">在左侧选择一个项目，或点击「新建项目」开始构建</div>
    </div>

    <template v-else>
      <!-- 顶部项目信息 -->
      <div class="chat-header">
        <div class="chat-header-top">
          <div class="chat-header-main">
            <div class="chat-project-name">{{ store.currentProject?.name || store.currentId }}</div>
          </div>
          <div class="chat-header-actions">
            <div class="top-tools">
              <button type="button" class="top-tool-btn" @click="openDrawer('roles')">
                角色输出
              </button>
              <button type="button" class="top-tool-btn" @click="openDrawer('progress')">
                任务进度
              </button>
              <button type="button" class="top-tool-btn" @click="openDrawer('debug')">
                调试
              </button>
            </div>

            <div class="model-control">
              <button type="button" class="model-pill" @click="openModelEditor">
                <span class="model-pill-name">{{ currentProviderShort }}</span>
                <span class="model-pill-separator">,</span>
                <span class="model-pill-version">{{ currentModelShortLabel }}</span>
              </button>

              <div v-if="modelEditorOpen" class="model-editor-popover">
                <label class="model-editor-field">
                  <span>模型提供方</span>
                  <select v-model="draftProvider" class="model-select">
                    <option
                      v-for="provider in providerOptions"
                      :key="provider.id"
                      :value="provider.id"
                    >
                      {{ provider.name }}
                    </option>
                  </select>
                </label>
                <label class="model-editor-field">
                  <span>模型版本</span>
                  <select
                    v-model="draftModel"
                    class="model-input"
                  >
                    <option
                      v-for="option in draftProviderModelOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label class="model-editor-field">
                  <span>智能</span>
                  <select v-model="draftEffort" class="model-input">
                    <option
                      v-for="option in draftProviderEffortOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label class="model-editor-field">
                  <span>速度</span>
                  <select v-model="draftSpeed" class="model-input">
                    <option
                      v-for="option in draftProviderSpeedOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <div class="model-editor-hint">保存后对后续阶段生效。</div>
                <div v-if="modelSaveError" class="model-editor-error">{{ modelSaveError }}</div>
                <div class="model-editor-actions">
                  <button type="button" class="btn ghost small" @click="closeModelEditor">取消</button>
                  <button
                    type="button"
                    class="btn primary small"
                    :disabled="modelSaving"
                    @click="saveModelConfig"
                  >
                    {{ modelSaving ? '保存中...' : '保存' }}
                  </button>
                </div>
              </div>
            </div>

            <div class="chat-status" :class="store.wsStatus">
              <span class="status-indicator" :class="store.wsStatus"></span>
              {{ wsStatusLabel }}
            </div>
          </div>
        </div>
        <div
          v-if="projectCodePath"
          class="chat-project-path"
          :class="{ expanded: pathExpanded }"
          :title="projectCodePath"
          @click="toggleProjectPath"
        >
          <span class="path-label">代码路径</span>
          <span class="path-value">{{ visibleProjectCodePath }}</span>
          <span class="path-toggle">{{ pathExpanded ? '收起' : '展开' }}</span>
          <button type="button" class="path-copy-btn" @click.stop="copyProjectPath">
            {{ pathCopied ? '已复制' : '复制' }}
          </button>
        </div>
      </div>

      <!-- 消息流 -->
      <div class="messages-container" ref="scrollRef">
        <div v-if="store.messages.length === 0 && store.wsStatus === 'connecting'" class="loading-hint">
          <span class="spinner"></span> 正在连接...
        </div>

        <transition-group name="fade-slide" tag="div" class="messages-list">
          <StageCard
            v-for="msg in store.messages"
            :key="msg.id"
            :msg="msg"
            :project-state="store.stateSnapshot"
          />
        </transition-group>

        <div v-if="store.chatMessages.length" class="chat-events">
          <div
            v-for="event in store.chatMessages"
            :key="event.id"
            class="chat-event"
            :class="event.kind"
          >
            <span class="chat-event-kind">{{ eventKindLabel(event.kind) }}</span>
            <span class="chat-event-text">{{ event.text }}</span>
          </div>
        </div>

        <!-- 运行中指示器 -->
        <div v-if="store.wsStatus === 'running'" class="running-indicator">
          <span class="pulse-dot"></span>
          <span>{{ runningLabel }} 处理中...</span>
        </div>

        <!-- 错误提示 -->
        <div v-if="store.wsStatus === 'error'" class="error-banner">
          ! {{ store.errorMsg }}
        </div>

        <!-- 完成横幅 -->
        <div v-if="store.wsStatus === 'done'" class="done-banner">
          完成 流水线完成！
        </div>
      </div>

      <ChatComposer />

      <RoleOutputDrawer
        v-if="activeDrawer === 'roles'"
        :project-state="store.stateSnapshot"
        :task-context="store.taskContext"
        @close="activeDrawer = ''"
      />
      <TaskProgressDrawer
        v-if="activeDrawer === 'progress'"
        :task-context="store.taskContext"
        @close="activeDrawer = ''"
      />
      <DebugDrawer
        v-if="activeDrawer === 'debug'"
        @close="activeDrawer = ''"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, watch, computed, nextTick, onMounted } from 'vue'
import { useProjectStore } from '../stores/project.js'
import StageCard from './StageCard.vue'
import ChatComposer from './ChatComposer.vue'
import RoleOutputDrawer from './RoleOutputDrawer.vue'
import TaskProgressDrawer from './TaskProgressDrawer.vue'
import DebugDrawer from './DebugDrawer.vue'

const store     = useProjectStore()
const scrollRef = ref(null)
const modelEditorOpen = ref(false)
const draftProvider = ref('')
const draftModel = ref('')
const draftEffort = ref('')
const draftSpeed = ref('')
const modelSaving = ref(false)
const modelSaveError = ref('')
const activeDrawer = ref('')
const pathCopied = ref(false)
const pathExpanded = ref(false)

const STATUS_LABELS = {
  idle: '待机', connecting: '连接中', running: '运行中',
  waiting: '等待决策', done: '已完成', error: '错误', report_breakpoint: '报告断点',
}
const STAGE_LABELS = {
  ceo: 'CEO',
  market_research_v1: '市场调研 v1',
  design_lead_v1: '设计负责人 v1',
  ceo_review_market: 'CEO复核市场',
  ceo_review_design: 'CEO复核设计',
  ceo_synthesis_review: 'CEO综合复核',
  market_research_v2: '市场调研 v2',
  design_lead_v2: '设计负责人 v2',
  report_breakpoint: '报告断点',
  pm: '产品经理', cto: 'CTO', backend: '后端',
  frontend: '前端', implementer: '代码实现', fixer: '修复', tester: 'QA', acceptance: '验收',
}

const wsStatusLabel = computed(() => STATUS_LABELS[store.wsStatus] || store.wsStatus)
const runningLabel  = computed(() => STAGE_LABELS[store.currentStage] || store.currentStage || '')
const fallbackProviders = [
  {
    id: 'codex',
    name: 'Codex 套餐模型',
    description: '通过 Codex CLI 使用当前 ChatGPT/Codex 登录态，不需要 API Key。',
    supports_custom_model: true,
    default_model: 'gpt-5.5',
    default_effort: 'high',
    default_speed: 'standard',
    model_options: [
      { label: 'GPT-5.5', value: 'gpt-5.5' },
      { label: 'GPT-5.4', value: 'gpt-5.4' },
      { label: 'GPT-5.4-Mini', value: 'gpt-5.4-mini' },
      { label: 'GPT-5.3-Codex', value: 'gpt-5.3-codex' },
      { label: 'GPT-5.3-Codex-Spark', value: 'gpt-5.3-codex-spark' },
      { label: 'GPT-5.2', value: 'gpt-5.2' },
    ],
    effort_options: [
      { label: '低', value: 'low' },
      { label: '中', value: 'medium' },
      { label: '高', value: 'high' },
      { label: '超高', value: 'xhigh' },
    ],
    speed_options: [
      { label: '标准', value: 'standard' },
      { label: '快速', value: 'fast' },
    ],
  },
]
const providerOptions = computed(() =>
  store.llmProviders.length ? store.llmProviders : fallbackProviders
)
const currentProviderId = computed(() =>
  store.currentProject?.llm_provider || store.defaultProvider || 'codex'
)
const currentProvider = computed(() =>
  providerOptions.value.find(p => p.id === currentProviderId.value) || providerOptions.value[0]
)
const currentProviderName = computed(() => currentProvider.value?.name || currentProviderId.value)
const currentProviderShort = computed(() => {
  if (currentProviderId.value === 'claude_cli') return 'claude'
  return currentProviderId.value || 'codex'
})
const currentModel = computed(() => store.currentProject?.llm_model || currentProvider.value?.default_model || '')
const currentEffort = computed(() => store.currentProject?.llm_effort || currentProvider.value?.default_effort || 'high')
const currentSpeed = computed(() => store.currentProject?.llm_speed || currentProvider.value?.default_speed || 'standard')
const currentModelLabel = computed(() => optionLabel(currentProvider.value?.model_options, currentModel.value) || currentModel.value || '默认模型')
const currentModelShortLabel = computed(() => compactModelLabel(currentModelLabel.value))
const currentEffortLabel = computed(() => `智能 ${optionLabel(currentProvider.value?.effort_options, currentEffort.value) || currentEffort.value}`)
const currentSpeedLabel = computed(() => optionLabel(currentProvider.value?.speed_options, currentSpeed.value) || currentSpeed.value)
const projectCodePath = computed(() =>
  store.currentProject?.project_dir ||
  store.taskContext?.project?.project_dir ||
  store.stateSnapshot?.project_dir ||
  ''
)
const compactProjectCodePath = computed(() => {
  const path = projectCodePath.value
  if (!path) return ''
  const parts = path.split('/').filter(Boolean)
  if (parts.length <= 2) return path
  return parts.slice(-2).join('/')
})
const visibleProjectCodePath = computed(() =>
  pathExpanded.value ? projectCodePath.value : compactProjectCodePath.value
)
const draftProviderInfo = computed(() =>
  providerOptions.value.find(p => p.id === draftProvider.value) || currentProvider.value
)
const draftProviderModelOptions = computed(() => draftProviderInfo.value?.model_options || [])
const draftProviderEffortOptions = computed(() => draftProviderInfo.value?.effort_options || [])
const draftProviderSpeedOptions = computed(() => draftProviderInfo.value?.speed_options || [])

function optionLabel(options = [], value) {
  return (options || []).find(option => option.value === value)?.label || ''
}

function compactModelLabel(label = '') {
  if (!label || label === '默认模型') return label || '默认模型'
  return label
    .replace(/^GPT-/i, 'chat_gpt ')
    .replace(/^GPT/i, 'chat_gpt')
    .replace(/-/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function eventKindLabel(kind) {
  const labels = {
    user: '用户',
    progress: '过程',
    dispatch: 'CEO',
    system: '系统',
  }
  return labels[kind] || '消息'
}

function fillDraftDefaults(providerId) {
  const provider = providerOptions.value.find(p => p.id === providerId) || providerOptions.value[0]
  draftModel.value = provider?.default_model || provider?.model_options?.[0]?.value || ''
  draftEffort.value = provider?.default_effort || provider?.effort_options?.[0]?.value || ''
  draftSpeed.value = provider?.default_speed || provider?.speed_options?.[0]?.value || 'standard'
}

onMounted(() => {
  if (store.llmProviders.length === 0) {
    store.fetchLlmProviders()
  }
})

function openModelEditor() {
  draftProvider.value = currentProviderId.value
  draftModel.value = currentModel.value
  draftEffort.value = currentEffort.value
  draftSpeed.value = currentSpeed.value
  modelSaveError.value = ''
  modelEditorOpen.value = true
}

function closeModelEditor() {
  modelEditorOpen.value = false
  modelSaveError.value = ''
}

function openDrawer(name) {
  modelEditorOpen.value = false
  activeDrawer.value = activeDrawer.value === name ? '' : name
}

function toggleProjectPath() {
  pathExpanded.value = !pathExpanded.value
}

async function copyProjectPath() {
  if (!projectCodePath.value) return
  try {
    await navigator.clipboard.writeText(projectCodePath.value)
    pathCopied.value = true
    setTimeout(() => {
      pathCopied.value = false
    }, 1600)
  } catch (e) {
    console.error('copyProjectPath', e)
  }
}

async function saveModelConfig() {
  if (!store.currentId) return
  modelSaving.value = true
  modelSaveError.value = ''
  try {
    await store.updateProjectModel(store.currentId, {
      provider: draftProvider.value,
      model: draftModel.value || null,
      effort: draftEffort.value || null,
      speed: draftSpeed.value || null,
    })
    closeModelEditor()
  } catch (e) {
    modelSaveError.value = e.message || '模型配置保存失败'
  } finally {
    modelSaving.value = false
  }
}

// 新消息时自动滚动到底部
watch(
  () => [store.messages.length, store.chatMessages.length],
  async () => {
    await nextTick()
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  }
)
watch(
  () => store.wsStatus,
  async () => {
    await nextTick()
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  }
)
watch(
  () => store.currentId,
  () => {
    closeModelEditor()
    activeDrawer.value = ''
    pathExpanded.value = false
  }
)
watch(
  () => draftProvider.value,
  (providerId, previousProviderId) => {
    if (!modelEditorOpen.value || !previousProviderId || providerId === previousProviderId) return
    fillDraftDefaults(providerId)
  }
)
</script>

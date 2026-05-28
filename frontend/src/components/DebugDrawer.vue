<template>
  <div class="drawer-backdrop" @click.self="$emit('close')">
    <aside class="side-drawer debug-drawer">
      <div class="drawer-header">
        <div>
          <div class="drawer-kicker">调试模式</div>
          <h2>{{ title }}</h2>
        </div>
        <button class="drawer-close" type="button" @click="$emit('close')">×</button>
      </div>

      <div class="debug-toolbar">
        <button
          type="button"
          class="btn primary small"
          :disabled="store.debugLoading"
          @click="toggleDebug"
        >
          {{ debugEnabled ? '关闭调试' : '开启调试' }}
        </button>
        <button
          type="button"
          class="btn ghost small"
          :disabled="store.debugLoading"
          @click="store.fetchDebugTimeline()"
        >
          刷新
        </button>
      </div>

      <div class="debug-hint">
        调试模式会记录阶段开始、模型完成、产物解析、文件写入和等待确认。点击任意检查点可以查看详情并从该点重跑。
      </div>

      <div v-if="store.debugLoading" class="drawer-empty">正在读取调试时间线...</div>
      <div v-else-if="!debugEnabled" class="drawer-empty">调试模式未开启。</div>
      <div v-else-if="store.debugCheckpoints.length === 0" class="drawer-empty">暂无检查点，继续运行任务后会自动生成。</div>

      <div v-else class="debug-layout">
        <div class="debug-timeline">
          <button
            v-for="checkpoint in orderedCheckpoints"
            :key="checkpoint.id"
            type="button"
            class="debug-step"
            :class="{ active: selected?.id === checkpoint.id }"
            @click="selectCheckpoint(checkpoint)"
          >
            <span class="debug-dot" :class="checkpoint.status"></span>
            <span class="debug-main">
              <span class="debug-title">{{ checkpointTitle(checkpoint) }}</span>
              <span class="debug-meta">
                {{ stageLabel(checkpoint.stage) }}
                <template v-if="checkpoint.module"> / {{ checkpoint.module }}</template>
                · {{ kindLabel(checkpoint.kind) }}
              </span>
              <span class="debug-summary">{{ checkpoint.summary || '无摘要' }}</span>
            </span>
            <span class="debug-time">{{ formatTime(checkpoint.created_at) }}</span>
          </button>
        </div>

        <div v-if="selected" class="debug-detail">
          <div class="debug-detail-title">{{ checkpointTitle(selected) }}</div>
          <div class="debug-detail-meta">
            {{ stageLabel(selected.stage) }}
            <template v-if="selected.module"> / {{ selected.module }}</template>
            · {{ kindLabel(selected.kind) }}
          </div>
          <p class="debug-detail-summary">{{ selected.summary || '无摘要' }}</p>

          <section class="debug-generated">
            <div class="debug-section-title">生成内容</div>
            <div v-if="detailLoading" class="debug-output-empty">正在读取生成内容...</div>
            <StageCard
              v-else-if="generatedMsg"
              :msg="generatedMsg"
              :project-state="detail?.state || store.stateSnapshot"
            />
            <div v-else class="debug-output-empty">
              这个检查点还没有可展示的生成内容。
            </div>
          </section>

          <label class="debug-feedback">
            <span>重跑说明</span>
            <textarea
              v-model="rerunFeedback"
              placeholder="例如：从这里开始，客户管理模块改成更完整的列表、详情、编辑和筛选。"
            />
          </label>

          <div class="debug-actions">
            <button
              type="button"
              class="btn primary small"
              :disabled="rerunning"
              @click="rerunSelected"
            >
              {{ rerunning ? '已提交...' : '从这里重跑' }}
            </button>
            <button type="button" class="btn ghost small" @click="toggleRawDetail">
              {{ showRawDetail ? '隐藏原始数据' : '查看原始数据' }}
            </button>
          </div>

          <pre v-if="showRawDetail && detail" class="debug-json">{{ detailPreview }}</pre>
          <div v-if="error" class="model-editor-error">{{ error }}</div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useProjectStore } from '../stores/project.js'
import StageCard from './StageCard.vue'

defineEmits(['close'])

const store = useProjectStore()
const selected = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const rerunFeedback = ref('')
const rerunning = ref(false)
const showRawDetail = ref(false)
const error = ref('')

const STAGE_LABELS = {
  ceo: 'CEO',
  pm: '产品经理',
  cto: 'CTO',
  backend: '后端',
  frontend: '前端',
  implementer: '代码实现',
  fixer: '修复',
  tester: 'QA',
  acceptance: '验收',
}

const KIND_LABELS = {
  state_snapshot: '历史快照',
  stage_started: '阶段开始',
  model_started: '模型开始',
  model_completed: '模型完成',
  artifact_parsed: '产物解析',
  file_ops_applied: '文件写入',
  interrupt: '等待确认',
  rerun_requested: '重跑请求',
  complete: '完成',
  error: '错误',
}

const title = computed(() => store.currentProject?.name || store.currentId || '当前项目')
const debugEnabled = computed(() => !!store.debugSession?.enabled)
const orderedCheckpoints = computed(() =>
  [...store.debugCheckpoints].sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
)
const detailPreview = computed(() => JSON.stringify(detail.value, null, 2))
const STAGE_STATE_KEYS = {
  ceo: 'brief',
  pm: 'features',
  cto: 'tech_plan',
  backend: 'api_spec',
  frontend: 'ui_spec',
  implementer: 'code_files',
  fixer: 'test_report',
  tester: 'test_report',
  acceptance: 'acceptance',
}
const STAGE_MARKS = {
  ceo: 'CEO',
  pm: 'PM',
  cto: 'CTO',
  backend: 'API',
  frontend: 'UI',
  implementer: 'CODE',
  fixer: 'FIX',
  tester: 'QA',
  acceptance: 'OK',
}
const generatedData = computed(() => pickGeneratedData())
const generatedMsg = computed(() => {
  if (!selected.value || !generatedData.value) return null
  const stage = selected.value.stage
  return {
    id: `debug-output-${selected.value.id}`,
    stage,
    emoji: STAGE_MARKS[stage] || 'STEP',
    title: `${checkpointTitle(selected.value)} · 生成内容`,
    data: normalizeStageData(stage, generatedData.value),
    extra: generatedExtra.value,
    status: selected.value.status === 'waiting' ? 'waiting' : 'done',
  }
})
const generatedExtra = computed(() => {
  if (selected.value?.stage !== 'implementer') return {}
  const data = normalizeStageData('implementer', generatedData.value)
  const total = data?.files?.length || 0
  return { progress: total ? `${total}/${total}` : '', remaining: 0, module: selected.value?.module }
})

onMounted(async () => {
  await store.fetchDebugTimeline()
  selected.value = orderedCheckpoints.value.at(-1) || null
})

watch(
  selected,
  () => {
    loadDetail()
  },
  { immediate: false }
)

function stageLabel(stage) {
  return STAGE_LABELS[stage] || stage || '未知阶段'
}

function kindLabel(kind) {
  return KIND_LABELS[kind] || kind || '检查点'
}

function checkpointTitle(checkpoint) {
  return checkpoint.title || `${stageLabel(checkpoint.stage)} ${kindLabel(checkpoint.kind)}`
}

function formatTime(ts) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function selectCheckpoint(checkpoint) {
  selected.value = checkpoint
  detail.value = null
  rerunFeedback.value = ''
  showRawDetail.value = false
  error.value = ''
}

async function toggleDebug() {
  error.value = ''
  try {
    if (debugEnabled.value) {
      await store.disableDebugMode()
    } else {
      await store.enableDebugMode()
      selected.value = orderedCheckpoints.value.at(-1) || null
    }
  } catch (err) {
    error.value = err.message || '调试模式切换失败'
  }
}

async function loadDetail() {
  if (!selected.value) return
  error.value = ''
  detailLoading.value = true
  const checkpointId = selected.value.id
  try {
    const nextDetail = await store.fetchDebugCheckpoint(checkpointId)
    if (selected.value?.id === checkpointId) {
      detail.value = nextDetail
    }
  } catch (err) {
    error.value = err.message || '读取详情失败'
  } finally {
    if (selected.value?.id === checkpointId) {
      detailLoading.value = false
    }
  }
}

async function toggleRawDetail() {
  if (!detail.value) {
    await loadDetail()
  }
  showRawDetail.value = !showRawDetail.value
}

async function rerunSelected() {
  if (!selected.value) return
  rerunning.value = true
  error.value = ''
  try {
    await store.rerunDebugCheckpoint(selected.value, rerunFeedback.value)
  } catch (err) {
    error.value = err.message || '重跑失败'
  } finally {
    rerunning.value = false
  }
}

function isMeaningful(value) {
  if (value === null || value === undefined) return false
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'object') return Object.keys(value).length > 0
  return String(value).trim().length > 0
}

function isStageOutput(stage, value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return stage === 'implementer' && Array.isArray(value) && value.length > 0
  }
  const checks = {
    ceo: ['project_name', 'goal', 'scope'],
    pm: ['features', 'overview'],
    cto: ['language', 'framework', 'modules'],
    backend: ['data_models', 'endpoints'],
    frontend: ['pages', 'shared_components'],
    tester: ['passed', 'failed', 'cases'],
    fixer: ['passed', 'failed', 'summary'],
    acceptance: ['passed', 'accepted', 'verdict'],
  }
  return (checks[stage] || []).some(key => Object.prototype.hasOwnProperty.call(value, key))
}

function pickGeneratedData() {
  if (!selected.value || !detail.value) return null
  const stage = selected.value.stage
  const stateKey = STAGE_STATE_KEYS[stage]
  const stateValue = stateKey ? detail.value.state?.[stateKey] : null
  const outputValue = detail.value.output

  if (isStageOutput(stage, outputValue)) return outputValue
  if (isMeaningful(stateValue)) return stateValue
  if (isMeaningful(outputValue)) return outputValue
  return null
}

function normalizeStageData(stage, data) {
  if (stage === 'implementer' && Array.isArray(data)) {
    return {
      files: data.map(item => {
        if (typeof item === 'string') return item
        return item?.path || item?.description || JSON.stringify(item)
      }),
    }
  }
  return data
}
</script>

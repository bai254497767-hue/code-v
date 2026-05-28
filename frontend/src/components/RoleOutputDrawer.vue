<template>
  <div class="drawer-backdrop" @click.self="$emit('close')">
    <aside class="side-drawer" aria-label="角色输出">
      <div class="drawer-header">
        <div>
          <div class="drawer-kicker">角色输出</div>
          <h2>团队产出</h2>
        </div>
        <button class="drawer-close" type="button" @click="$emit('close')">×</button>
      </div>

      <div class="drawer-body role-output-layout">
        <div class="role-tabs">
          <button
            v-for="role in roles"
            :key="role.stage"
            type="button"
            class="role-tab"
            :class="{ active: selectedStage === role.stage, ready: role.ready }"
            @click="selectedStage = role.stage"
          >
            <span class="role-tab-icon">{{ role.icon }}</span>
            <span class="role-tab-main">
              <span class="role-tab-name">{{ role.name }}</span>
              <span class="role-tab-summary">{{ role.summary }}</span>
            </span>
            <span class="role-tab-state">{{ roleStateLabel(role.status, role.ready) }}</span>
          </button>
        </div>

        <section class="role-output-panel">
          <div class="role-output-title">
            <span>{{ selectedRole.icon }}</span>
            <div>
              <h3>{{ selectedRole.name }}</h3>
              <p>{{ selectedRole.summary }}</p>
            </div>
          </div>

          <div v-if="selectedVersionsList.length > 1" class="version-tabs role-version-tabs">
            <button
              v-for="item in selectedVersionsList"
              :key="`${selectedRole.stage}-${versionKey(item)}`"
              type="button"
              class="version-tab"
              :class="{ active: selectedVersionKey === versionKey(item) }"
              @click="selectVersion(selectedRole.stage, item)"
            >
              {{ versionLabel(item, selectedVersionsList) }}
            </button>
          </div>

          <component
            v-if="selectedRole.ready && selectedComponent"
            :is="selectedComponent"
            :data="selectedData"
            :extra="selectedExtra"
            :project-state="projectState"
            :variant="selectedReportVariant"
          />
          <div v-else class="drawer-empty">
            这个角色还没有可查看的输出。
          </div>
        </section>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, ref, watch } from 'vue'

const props = defineProps({
  projectState: { type: Object, default: () => ({}) },
  taskContext: { type: Object, default: null },
})
defineEmits(['close'])

const roleDefs = [
  { stage: 'ceo', key: 'brief', icon: 'CEO', name: 'CEO' },
  { stage: 'market', key: 'market_reports', icon: 'MKT', name: '市场调研人员', versions: true },
  { stage: 'design', key: 'design_reports', icon: 'DSN', name: '设计负责人', versions: true },
  { stage: 'ceo_reviews', key: 'ceo_reviews', icon: 'REV', name: 'CEO 复核', versions: true },
  { stage: 'ceo_synthesis', key: 'synthesis_report', icon: 'SYN', name: 'CEO 综合复核' },
  { stage: 'pm', key: 'features', icon: 'PM', name: '产品经理' },
  { stage: 'cto', key: 'tech_plan', icon: 'CTO', name: 'CTO' },
  { stage: 'backend', key: 'api_spec', icon: 'API', name: '后端工程师' },
  { stage: 'frontend', key: 'ui_spec', icon: 'UI', name: '前端工程师' },
  { stage: 'implementer', key: 'code_files', icon: 'CODE', name: '实现工程师' },
  { stage: 'tester', key: 'test_report', icon: 'QA', name: '测试工程师' },
  { stage: 'acceptance', key: 'acceptance', icon: 'OK', name: '产品验收' },
]

const stageComponents = {
  ceo: defineAsyncComponent(() => import('./stages/CeoStage.vue')),
  market: defineAsyncComponent(() => import('./stages/ReportStage.vue')),
  design: defineAsyncComponent(() => import('./stages/ReportStage.vue')),
  ceo_reviews: defineAsyncComponent(() => import('./stages/ReportStage.vue')),
  ceo_synthesis: defineAsyncComponent(() => import('./stages/ReportStage.vue')),
  pm: defineAsyncComponent(() => import('./stages/PmStage.vue')),
  cto: defineAsyncComponent(() => import('./stages/CtoStage.vue')),
  backend: defineAsyncComponent(() => import('./stages/BackendStage.vue')),
  frontend: defineAsyncComponent(() => import('./stages/FrontendStage.vue')),
  implementer: defineAsyncComponent(() => import('./stages/ImplementerStage.vue')),
  tester: defineAsyncComponent(() => import('./stages/TesterStage.vue')),
  acceptance: defineAsyncComponent(() => import('./stages/AcceptanceStage.vue')),
}

const selectedStage = ref('ceo')
const selectedVersions = ref({})

const roles = computed(() => roleDefs.map(def => {
  const data = props.projectState?.[def.key]
  const status = props.taskContext?.stages?.[def.stage]?.status || 'pending'
  const summary = props.taskContext?.stages?.[def.stage]?.summary || summarize(def.stage, data)
  const ready = data !== null && data !== undefined && !(Array.isArray(data) && data.length === 0)
  const versions = def.versions && Array.isArray(data) ? sortedVersions(data) : []
  return { ...def, data, versions, ready, status, summary }
}))

const selectedRole = computed(() =>
  roles.value.find(role => role.stage === selectedStage.value) || roles.value[0]
)
const selectedComponent = computed(() => stageComponents[selectedRole.value?.stage])
const selectedVersionsList = computed(() => selectedRole.value?.versions || [])
const selectedVersionKey = computed(() => selectedVersions.value[selectedRole.value?.stage] || '')
const selectedReportVariant = computed(() =>
  ['market', 'design', 'ceo_reviews', 'ceo_synthesis'].includes(selectedRole.value?.stage)
    ? 'document'
    : 'cards'
)
const selectedData = computed(() => {
  const role = selectedRole.value
  if (role?.stage === 'implementer' && Array.isArray(role.data)) {
    return {
      files: role.data.map(file => file.path || file.description || String(file)),
    }
  }
  if (role?.versions?.length) {
    const key = selectedVersions.value[role.stage]
    return role.versions.find(item => versionKey(item) === key) || latestVersion(role.versions)
  }
  return role?.data
})
const selectedExtra = computed(() => {
  if (selectedRole.value?.stage === 'implementer') {
    return { progress: `${selectedData.value?.files?.length || 0}/${selectedData.value?.files?.length || 0}`, remaining: 0 }
  }
  return {}
})

watch(
  () => roles.value,
  (items) => {
    const nextSelectedVersions = { ...selectedVersions.value }
    for (const role of items) {
      if (!role.versions?.length) continue
      const currentKey = nextSelectedVersions[role.stage]
      if (!currentKey || !role.versions.some(item => versionKey(item) === currentKey)) {
        nextSelectedVersions[role.stage] = versionKey(latestVersion(role.versions))
      }
    }
    selectedVersions.value = nextSelectedVersions
    if (!items.some(role => role.stage === selectedStage.value && role.ready)) {
      selectedStage.value = items.find(role => role.ready)?.stage || 'ceo'
    }
  },
  { immediate: true }
)

function roleStateLabel(status, ready) {
  if (status === 'running') return '处理中'
  if (status === 'waiting') return '待确认'
  if (status === 'error') return '异常'
  return ready ? '已产出' : '未开始'
}

function sortedVersions(items) {
  return [...(items || [])].sort((a, b) => {
    const versionA = Number(a?.version || 0)
    const versionB = Number(b?.version || 0)
    if (versionA !== versionB) return versionA - versionB
    return Number(a?.created_at || 0) - Number(b?.created_at || 0)
  })
}

function latestVersion(items) {
  return items?.[items.length - 1] || null
}

function versionKey(item) {
  return `${item?.version || 'x'}-${item?.role || item?.stage || ''}-${item?.created_at || ''}`
}

function versionLabel(item, items = []) {
  if (item?.version) {
    const sameVersion = items.filter(entry => Number(entry?.version || 0) === Number(item.version))
    if (sameVersion.length > 1) {
      const runIndex = sameVersion.findIndex(entry => versionKey(entry) === versionKey(item)) + 1
      return `v${item.version} · 第 ${runIndex} 次`
    }
    return `v${item.version}`
  }
  if (item?.role) return item.role
  return '版本'
}

function selectVersion(stage, item) {
  selectedVersions.value = { ...selectedVersions.value, [stage]: versionKey(item) }
}

function summarize(stage, data) {
  if (!data) return '等待产出'
  if (stage === 'ceo') return data.project_name || '项目立项完成'
  if (stage === 'market') return summarizeReportVersions(data, '市场调研')
  if (stage === 'design') return summarizeReportVersions(data, '设计报告')
  if (stage === 'ceo_reviews') return `${Array.isArray(data) ? data.length : 0} 条 CEO 复核`
  if (stage === 'ceo_synthesis') return data.summary || 'CEO 综合复核完成'
  if (stage === 'pm') return `已拆解 ${data.features?.length || 0} 个功能`
  if (stage === 'cto') return [data.language, data.framework].filter(Boolean).join(' / ') || '技术方案完成'
  if (stage === 'backend') return `${data.data_models?.length || 0} 个模型，${data.endpoints?.length || 0} 个接口`
  if (stage === 'frontend') return `${data.pages?.length || 0} 个页面`
  if (stage === 'implementer') return `${Array.isArray(data) ? data.length : 0} 个代码文件`
  if (stage === 'tester') return `通过 ${data.passed || 0}，失败 ${data.failed || 0}`
  if (stage === 'acceptance') return data.accepted || data.passed ? '验收通过' : '验收未通过'
  return '已产出'
}

function summarizeReportVersions(data, label) {
  const items = Array.isArray(data) ? data : []
  if (!items.length) return '等待产出'
  const versions = [...new Set(items.map(item => Number(item?.version || 0)).filter(Boolean))]
  if (versions.length <= 1) {
    const version = versions[0] ? `v${versions[0]}` : '未标版本'
    return `${version}，${items.length} 次${label}产出`
  }
  return `${versions.length} 个${label}版本，${items.length} 次产出`
}
</script>

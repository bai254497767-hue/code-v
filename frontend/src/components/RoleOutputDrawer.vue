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

          <component
            v-if="selectedRole.ready && selectedComponent"
            :is="selectedComponent"
            :data="selectedData"
            :extra="selectedExtra"
            :project-state="projectState"
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
  { stage: 'ceo', key: 'brief', icon: '🏢', name: 'CEO' },
  { stage: 'pm', key: 'features', icon: '📋', name: '产品经理' },
  { stage: 'cto', key: 'tech_plan', icon: '🔧', name: 'CTO' },
  { stage: 'backend', key: 'api_spec', icon: '🗄️', name: '后端工程师' },
  { stage: 'frontend', key: 'ui_spec', icon: '🎨', name: '前端工程师' },
  { stage: 'implementer', key: 'code_files', icon: '💻', name: '实现工程师' },
  { stage: 'tester', key: 'test_report', icon: '🧪', name: '测试工程师' },
  { stage: 'acceptance', key: 'acceptance', icon: '✅', name: '产品验收' },
]

const stageComponents = {
  ceo: defineAsyncComponent(() => import('./stages/CeoStage.vue')),
  pm: defineAsyncComponent(() => import('./stages/PmStage.vue')),
  cto: defineAsyncComponent(() => import('./stages/CtoStage.vue')),
  backend: defineAsyncComponent(() => import('./stages/BackendStage.vue')),
  frontend: defineAsyncComponent(() => import('./stages/FrontendStage.vue')),
  implementer: defineAsyncComponent(() => import('./stages/ImplementerStage.vue')),
  tester: defineAsyncComponent(() => import('./stages/TesterStage.vue')),
  acceptance: defineAsyncComponent(() => import('./stages/AcceptanceStage.vue')),
}

const selectedStage = ref('ceo')

const roles = computed(() => roleDefs.map(def => {
  const data = props.projectState?.[def.key]
  const status = props.taskContext?.stages?.[def.stage]?.status || 'pending'
  const summary = props.taskContext?.stages?.[def.stage]?.summary || summarize(def.stage, data)
  const ready = data !== null && data !== undefined && !(Array.isArray(data) && data.length === 0)
  return { ...def, data, ready, status, summary }
}))

const selectedRole = computed(() =>
  roles.value.find(role => role.stage === selectedStage.value) || roles.value[0]
)
const selectedComponent = computed(() => stageComponents[selectedRole.value?.stage])
const selectedData = computed(() => {
  const role = selectedRole.value
  if (role?.stage === 'implementer' && Array.isArray(role.data)) {
    return {
      files: role.data.map(file => file.path || file.description || String(file)),
    }
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

function summarize(stage, data) {
  if (!data) return '等待产出'
  if (stage === 'ceo') return data.project_name || '项目立项完成'
  if (stage === 'pm') return `已拆解 ${data.features?.length || 0} 个功能`
  if (stage === 'cto') return [data.language, data.framework].filter(Boolean).join(' / ') || '技术方案完成'
  if (stage === 'backend') return `${data.data_models?.length || 0} 个模型，${data.endpoints?.length || 0} 个接口`
  if (stage === 'frontend') return `${data.pages?.length || 0} 个页面`
  if (stage === 'implementer') return `${Array.isArray(data) ? data.length : 0} 个代码文件`
  if (stage === 'tester') return `通过 ${data.passed || 0}，失败 ${data.failed || 0}`
  if (stage === 'acceptance') return data.accepted || data.passed ? '验收通过' : '验收未通过'
  return '已产出'
}
</script>

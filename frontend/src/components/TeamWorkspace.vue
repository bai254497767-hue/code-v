<template>
  <div class="team-workspace">
    <div class="team-workspace-title">团队工作区</div>
    <div class="team-role-list">
      <div
        v-for="role in roles"
        :key="role.stage"
        class="team-role-item"
        :class="{ ready: role.ready, open: expanded.has(role.stage) }"
      >
        <button class="team-role-header" type="button" @click="toggle(role.stage)">
          <span class="team-role-icon">{{ role.icon }}</span>
          <span class="team-role-main">
            <span class="team-role-name">{{ role.name }}</span>
            <span class="team-role-meta">{{ role.ready ? role.summary : '等待产出' }}</span>
          </span>
          <span class="team-role-state">{{ role.ready ? '已产出' : '未开始' }}</span>
          <span class="expand-icon">{{ expanded.has(role.stage) ? '▲' : '▼' }}</span>
        </button>

        <div v-if="expanded.has(role.stage)" class="team-role-body">
          <div v-if="role.ready" class="team-output-wrap">
            <div v-if="role.versions?.length > 1" class="version-tabs">
              <button
                v-for="item in role.versions"
                :key="`${role.stage}-${item.version || item.created_at}`"
                type="button"
                class="version-tab"
                :class="{ active: selectedVersions[role.stage] === versionKey(item) }"
                @click="selectVersion(role.stage, item)"
              >
                v{{ item.version || '-' }}
              </button>
            </div>
            <pre class="team-output">{{ formatOutput(selectedRoleData(role)) }}</pre>
          </div>
          <div v-else class="team-empty">该角色还没有产出内容。</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  projectState: { type: Object, default: () => ({}) },
})

const expanded = ref(new Set())

const roleDefs = [
  { stage: 'ceo', key: 'brief', icon: 'CEO', name: 'CEO', summary: data => data?.project_name || '项目立项完成' },
  { stage: 'market', key: 'market_reports', icon: 'MKT', name: '市场调研人员', versions: true, summary: data => summarizeReportVersions(data, '市场调研') },
  { stage: 'design', key: 'design_reports', icon: 'DSN', name: '设计负责人', versions: true, summary: data => summarizeReportVersions(data, '设计报告') },
  { stage: 'ceo_reviews', key: 'ceo_reviews', icon: 'REV', name: 'CEO 复核', versions: true, summary: data => `${data?.length || 0} 条复核` },
  { stage: 'ceo_synthesis', key: 'synthesis_report', icon: 'SYN', name: 'CEO 综合复核', summary: data => data?.summary || '综合复核完成' },
  { stage: 'pm', key: 'features', icon: 'PM', name: '产品经理', summary: data => `${data?.features?.length || 0} 个功能模块` },
  { stage: 'cto', key: 'tech_plan', icon: 'CTO', name: 'CTO', summary: data => `${data?.language || ''} / ${data?.framework || ''}`.trim() || '技术方案完成' },
  { stage: 'backend', key: 'api_spec', icon: 'API', name: '后端工程师', summary: data => `${data?.data_models?.length || 0} 个模型，${data?.endpoints?.length || 0} 个 API` },
  { stage: 'frontend', key: 'ui_spec', icon: 'UI', name: '前端工程师', summary: data => `${data?.pages?.length || 0} 个页面` },
  { stage: 'implementer', key: 'code_files', icon: 'CODE', name: '实现工程师', summary: data => `${Array.isArray(data) ? data.length : 0} 个代码文件` },
  { stage: 'tester', key: 'test_report', icon: 'QA', name: '测试工程师', summary: data => `通过 ${data?.passed || 0}，失败 ${data?.failed || 0}` },
  { stage: 'acceptance', key: 'acceptance', icon: 'OK', name: '验收', summary: data => data?.accepted ? '验收通过' : '验收未通过' },
]

const roles = computed(() => roleDefs.map(def => {
  const data = props.projectState?.[def.key]
  const ready = data !== null && data !== undefined && !(Array.isArray(data) && data.length === 0)
  const versions = def.versions && Array.isArray(data) ? data : []
  return {
    ...def,
    data,
    versions,
    ready,
    summary: ready ? def.summary(data) : '',
  }
}))
const selectedVersions = ref({})

function toggle(stage) {
  const next = new Set(expanded.value)
  next.has(stage) ? next.delete(stage) : next.add(stage)
  expanded.value = next
}

function formatOutput(data) {
  return JSON.stringify(data, null, 2)
}

function versionKey(item) {
  return `${item?.version || 'x'}-${item?.role || item?.stage || ''}-${item?.created_at || ''}`
}

function selectedRoleData(role) {
  if (!role?.versions?.length) return role?.data
  const key = selectedVersions.value[role.stage]
  return role.versions.find(item => versionKey(item) === key) || role.versions[role.versions.length - 1]
}

function selectVersion(stage, item) {
  selectedVersions.value = { ...selectedVersions.value, [stage]: versionKey(item) }
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

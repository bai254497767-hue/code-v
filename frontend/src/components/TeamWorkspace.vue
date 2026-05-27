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
          <pre v-if="role.ready" class="team-output">{{ formatOutput(role.data) }}</pre>
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
  { stage: 'ceo', key: 'brief', icon: '🏢', name: 'CEO', summary: data => data?.project_name || '项目立项完成' },
  { stage: 'pm', key: 'features', icon: '📋', name: '产品经理', summary: data => `${data?.features?.length || 0} 个功能模块` },
  { stage: 'cto', key: 'tech_plan', icon: '🔧', name: 'CTO', summary: data => `${data?.language || ''} / ${data?.framework || ''}`.trim() || '技术方案完成' },
  { stage: 'backend', key: 'api_spec', icon: '🗄️', name: '后端工程师', summary: data => `${data?.data_models?.length || 0} 个模型，${data?.endpoints?.length || 0} 个 API` },
  { stage: 'frontend', key: 'ui_spec', icon: '🎨', name: '前端工程师', summary: data => `${data?.pages?.length || 0} 个页面` },
  { stage: 'implementer', key: 'code_files', icon: '💻', name: '实现工程师', summary: data => `${Array.isArray(data) ? data.length : 0} 个代码文件` },
  { stage: 'tester', key: 'test_report', icon: '🧪', name: '测试工程师', summary: data => `通过 ${data?.passed || 0}，失败 ${data?.failed || 0}` },
  { stage: 'acceptance', key: 'acceptance', icon: '✅', name: '验收', summary: data => data?.accepted ? '验收通过' : '验收未通过' },
]

const roles = computed(() => roleDefs.map(def => {
  const data = props.projectState?.[def.key]
  const ready = data !== null && data !== undefined && !(Array.isArray(data) && data.length === 0)
  return {
    ...def,
    data,
    ready,
    summary: ready ? def.summary(data) : '',
  }
}))

function toggle(stage) {
  const next = new Set(expanded.value)
  next.has(stage) ? next.delete(stage) : next.add(stage)
  expanded.value = next
}

function formatOutput(data) {
  return JSON.stringify(data, null, 2)
}
</script>

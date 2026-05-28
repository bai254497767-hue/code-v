<template>
  <div class="structured-report" :class="{ compact }">
    <section
      v-for="(entry, index) in entries"
      :key="entry.key"
      class="report-section-block"
      :class="`tone-${index % 5}`"
    >
      <div class="report-section-head">
        <span class="report-section-dot"></span>
        <h4>{{ labelFor(entry.key) }}</h4>
      </div>

      <p v-if="isPrimitive(entry.value)" class="report-text">
        {{ formatPrimitive(entry.value) }}
      </p>

      <div v-else-if="isPrimitiveArray(entry.value)" class="report-tags">
        <span v-for="item in entry.value" :key="String(item)" class="report-tag">
          {{ formatPrimitive(item) }}
        </span>
      </div>

      <div v-else-if="Array.isArray(entry.value)" class="report-card-list">
        <article
          v-for="(item, itemIndex) in entry.value"
          :key="`${entry.key}-${itemIndex}`"
          class="report-mini-card"
        >
          <StructuredReport
            v-if="isObject(item)"
            :data="item"
            :compact="true"
          />
          <p v-else class="report-text">{{ formatPrimitive(item) }}</p>
        </article>
      </div>

      <StructuredReport
        v-else-if="isObject(entry.value)"
        :data="entry.value"
        :compact="true"
      />
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'

defineOptions({ name: 'StructuredReport' })

const props = defineProps({
  data: { type: [Object, Array], default: () => ({}) },
  compact: { type: Boolean, default: false },
  exclude: { type: Array, default: () => [] },
})

const labelMap = {
  project_name: '项目名称',
  project_summary: '项目概述',
  background: '背景',
  industry_background: '行业背景',
  market_status: '市场现状',
  user_pain_points: '用户痛点',
  why_now: '为什么现在做',
  goal: '目标',
  business_goal: '商业目标',
  user_goal: '用户目标',
  technical_goal: '技术目标',
  ai_goal: 'AI 目标',
  scope: '范围',
  included: '包含',
  excluded: '不包含',
  assumptions: '假设',
  target_users: '目标用户',
  primary_users: '核心用户',
  secondary_users: '次级用户',
  payment_capability: '付费能力',
  usage_frequency: '使用频率',
  user_value: '长期价值',
  ai_analysis: 'AI 落地分析',
  ai_is_necessary: '是否需要 AI',
  ai_role: 'AI 角色',
  ai_scenarios: 'AI 场景',
  ai_capabilities: 'AI 能力',
  ai_barrier: 'AI 壁垒',
  data_flywheel: '数据闭环',
  ai_risks: 'AI 风险',
  technical_architecture: '技术架构',
  frontend: '前端',
  backend: '后端',
  database: '数据库',
  ai_stack: 'AI 技术栈',
  deployment: '部署',
  scalability: '扩展性',
  business_model: '商业模式',
  revenue_model: '收入模式',
  customer_acquisition: '获客方式',
  cost_structure: '成本结构',
  team: '团队',
  role: '角色',
  responsibility: '职责',
  priority: '优先级',
  mvp_plan: 'MVP 计划',
  must_have: '必须具备',
  should_not_do: '暂不做',
  validation_strategy: '验证策略',
  feasibility: '可行性',
  technical_feasibility: '技术可行性',
  resource_feasibility: '资源可行性',
  market_feasibility: '市场可行性',
  overall_risk: '总体风险',
  ceo_conclusion: 'CEO 结论',
  decision: '决策',
  reason: '原因',
  biggest_risk: '最大风险',
  core_opportunity: '核心机会',
  title: '标题',
  summary: '摘要',
  version: '版本',
  next_step: '下一步',
  feedback: '反馈',
  approved: '是否通过',
}

const entries = computed(() => {
  const source = Array.isArray(props.data)
    ? Object.fromEntries(props.data.map((item, index) => [`item_${index + 1}`, item]))
    : props.data || {}
  return Object.entries(source)
    .filter(([key, value]) => !props.exclude.includes(key) && value !== null && value !== undefined && value !== '')
    .map(([key, value]) => ({ key, value }))
})

function labelFor(key) {
  if (labelMap[key]) return labelMap[key]
  if (/^item_\d+$/.test(key)) return `条目 ${key.split('_')[1]}`
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isPrimitive(value) {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function isPrimitiveArray(value) {
  return Array.isArray(value) && value.every(isPrimitive)
}

function formatPrimitive(value) {
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (value === null || value === undefined) return ''
  return String(value)
}
</script>

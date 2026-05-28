<template>
  <div class="stage-content ceo-stage ceo-stage-modern">
    <section class="ceo-hero-report">
      <div class="ceo-hero-kicker">CEO 项目立项</div>
      <h3>{{ data?.project_name || '项目报告' }}</h3>
      <p>{{ data?.project_summary || data?.summary || 'CEO 已完成初步项目判断。' }}</p>
    </section>

    <div class="ceo-goal-grid">
      <article
        v-for="item in goalCards"
        :key="item.label"
        class="ceo-goal-card"
        :class="item.tone"
      >
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </div>

    <section class="ceo-team-block">
      <div class="report-section-head">
        <span class="report-section-dot"></span>
        <h4>团队工作区</h4>
      </div>
      <TeamWorkspace :project-state="projectState" />
    </section>

    <StructuredReport
      :data="data || {}"
      :exclude="['project_name', 'project_summary', 'summary', 'team']"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import TeamWorkspace from '../TeamWorkspace.vue'
import StructuredReport from '../StructuredReport.vue'

const props = defineProps({
  data: Object,
  extra: Object,
  projectState: { type: Object, default: () => ({}) },
})

const goalCards = computed(() => {
  const goal = props.data?.goal || {}
  const conclusion = props.data?.ceo_conclusion || {}
  return [
    { label: '商业目标', value: goal.business_goal || props.data?.goal || '待补充', tone: 'mint' },
    { label: '用户目标', value: goal.user_goal || '待补充', tone: 'orange' },
    { label: '核心机会', value: conclusion.core_opportunity || '待补充', tone: 'sky' },
  ].filter(item => item.value && item.value !== '待补充')
})
</script>

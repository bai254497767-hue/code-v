<template>
  <div class="stage-content ceo-stage">
    <div class="info-row">
      <span class="label">项目名称</span>
      <span class="value highlight">{{ data.project_name }}</span>
    </div>
    <div class="info-row">
      <span class="label">目标</span>
      <span class="value">{{ data.goal }}</span>
    </div>
    <div class="info-row">
      <span class="label">范围</span>
      <span class="value">{{ data.scope }}</span>
    </div>
    <div class="info-row">
      <span class="label">团队</span>
      <TeamWorkspace :project-state="projectState" />
    </div>
    <div class="info-row">
      <span class="label">可行性</span>
      <span class="value muted">{{ data.feasibility }}</span>
    </div>
  </div>
</template>

<script setup>
import TeamWorkspace from '../TeamWorkspace.vue'

defineProps({
  data: Object,
  extra: Object,
  projectState: { type: Object, default: () => ({}) },
})
</script>

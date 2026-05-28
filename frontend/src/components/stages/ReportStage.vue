<template>
  <div class="stage-content report-stage">
    <div class="info-row">
      <span class="label">标题</span>
      <span class="value highlight">{{ data?.title || data?.summary || '报告' }}</span>
    </div>
    <div v-if="data?.version" class="info-row">
      <span class="label">版本</span>
      <span class="value">v{{ data.version }}</span>
    </div>
    <div v-if="data?.summary" class="info-row">
      <span class="label">摘要</span>
      <span class="value">{{ data.summary }}</span>
    </div>
    <div v-if="data?.next_step" class="info-row">
      <span class="label">下一步</span>
      <span class="value">{{ data.next_step }}</span>
    </div>
    <pre class="report-json">{{ formatOutput(data) }}</pre>
  </div>
</template>

<script setup>
defineProps({
  data: Object,
  extra: Object,
  projectState: { type: Object, default: () => ({}) },
})

function formatOutput(data) {
  return JSON.stringify(data || {}, null, 2)
}
</script>

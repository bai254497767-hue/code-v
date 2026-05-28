<template>
  <div class="stage-content report-stage" :class="variant === 'document' ? 'report-stage-document' : 'report-stage-modern'">
    <section class="report-hero">
      <div class="report-hero-meta">
        <span v-if="data?.version">v{{ data.version }}</span>
        <span>{{ data?.kind || data?.report_kind || '报告' }}</span>
      </div>
      <h3>{{ data?.title || data?.summary || '阶段报告' }}</h3>
      <p v-if="data?.next_step">{{ data.next_step }}</p>
    </section>
    <StructuredReport :data="data || {}" :exclude="['title']" :layout="variant === 'document' ? 'document' : 'cards'" />
  </div>
</template>

<script setup>
import StructuredReport from '../StructuredReport.vue'

defineProps({
  data: Object,
  extra: Object,
  projectState: { type: Object, default: () => ({}) },
  variant: { type: String, default: 'cards' },
})
</script>

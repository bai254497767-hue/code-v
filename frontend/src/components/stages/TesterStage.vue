<template>
  <div class="stage-content tester-stage">
    <div class="test-summary-bar">
      <div class="test-stat pass">
        <span class="stat-num">{{ data.passed }}</span>
        <span class="stat-label">通过</span>
      </div>
      <div class="test-progress">
        <div class="progress-bar">
          <div class="progress-fill pass" :style="{ width: passPct + '%' }"></div>
        </div>
      </div>
      <div class="test-stat fail">
        <span class="stat-num">{{ data.failed }}</span>
        <span class="stat-label">失败</span>
      </div>
    </div>

    <p class="test-summary-text">{{ data.summary }}</p>

    <div class="cases-list">
      <div
        v-for="c in data.cases"
        :key="c.feature_id"
        class="case-row"
        :class="c.status"
      >
        <span class="case-icon">{{ c.status === 'pass' ? '✅' : '❌' }}</span>
        <span class="case-id">{{ c.feature_id }}</span>
        <span class="case-name">{{ c.feature_name }}</span>
        <span class="case-detail">{{ c.detail }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ data: Object, extra: Object })
const passPct = computed(() => {
  const total = (props.data?.passed || 0) + (props.data?.failed || 0)
  return total ? Math.round((props.data.passed / total) * 100) : 0
})
</script>

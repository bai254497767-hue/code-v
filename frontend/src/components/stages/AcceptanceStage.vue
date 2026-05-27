<template>
  <div class="stage-content acceptance-stage">
    <div class="verdict-icon" :class="data.passed ? 'pass' : 'fail'">
      {{ data.passed ? '✅' : '❌' }}
    </div>
    <div class="verdict-label" :class="data.passed ? 'pass' : 'fail'">
      {{ data.passed ? '验收通过' : '验收不通过' }}
    </div>
    <p class="verdict-text">{{ data.verdict }}</p>

    <div v-if="!data.passed && data.unmet_requirements?.length" class="unmet-list">
      <div class="unmet-title">未满足需求：</div>
      <div v-for="(item, i) in data.unmet_requirements" :key="i" class="unmet-item">
        <span class="unmet-icon">⚠️</span> {{ item }}
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ data: Object, extra: Object })
</script>

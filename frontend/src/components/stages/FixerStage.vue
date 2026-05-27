<template>
  <div class="stage-content fixer-stage">
    <div class="fix-header">
      <span class="fix-attempt">第 {{ extra.attempt || 1 }} 次修复</span>
      <div class="test-result">
        <span class="pass-count">✅ {{ data.passed }} 通过</span>
        <span class="fail-count">❌ {{ data.failed }} 失败</span>
      </div>
    </div>

    <p class="fix-summary">{{ data.summary }}</p>

    <div v-if="data.fixed_features?.length" class="fixed-features">
      <span v-for="f in data.fixed_features" :key="f" class="badge fix-badge">{{ f }}</span>
    </div>

    <div v-if="data.edits?.length" class="edits-list">
      <div v-for="(e, i) in data.edits" :key="i" class="edit-row">
        <span class="edit-icon">{{ editIcon(e) }}</span>
        <span class="edit-path">{{ e }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ data: Object, extra: Object })
const editIcon = e => e.includes('修改') ? '~' : e.includes('删除') ? '−' : '+'
</script>

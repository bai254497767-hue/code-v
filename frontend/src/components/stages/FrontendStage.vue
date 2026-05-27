<template>
  <div class="stage-content frontend-stage">
    <div class="section-title">页面列表</div>
    <div v-for="p in data.pages" :key="p.name" class="page-card">
      <div class="page-header">
        <span class="page-name">{{ p.name }}</span>
        <span class="page-route">{{ p.route }}</span>
      </div>
      <p class="page-desc">{{ p.description }}</p>
      <div class="components-list">
        <span v-for="c in p.components" :key="c" class="badge comp-badge">{{ c.split(' - ')[0] }}</span>
      </div>
    </div>

    <div class="section-title">共享组件</div>
    <div class="shared-comps">
      <span v-for="c in data.shared_components" :key="c" class="badge shared-badge">
        {{ c.split(' - ')[0] }}
      </span>
    </div>
  </div>
</template>

<script setup>
defineProps({ data: Object, extra: Object })
</script>

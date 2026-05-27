<template>
  <div class="stage-content cto-stage">
    <div class="tech-stack">
      <span class="badge lang-badge">{{ data.language }}</span>
      <span class="badge fw-badge">{{ data.framework }}</span>
    </div>
    <p class="arch-desc">{{ data.architecture }}</p>

    <div class="section-title">模块划分</div>
    <div class="modules-table">
      <div
        v-for="m in data.modules"
        :key="m.name"
        class="module-row"
      >
        <span class="module-name">{{ m.name }}</span>
        <span class="module-type" :class="m.type">{{ m.type }}</span>
        <span class="module-resp">{{ m.responsibility }}</span>
      </div>
    </div>

    <div class="section-title">开发阶段</div>
    <div class="phases-timeline">
      <div v-for="(p, i) in data.dev_phases" :key="i" class="phase-item">
        <span class="phase-num">{{ i + 1 }}</span>
        <span class="phase-text">{{ p }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ data: Object, extra: Object })
</script>

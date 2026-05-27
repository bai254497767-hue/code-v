<template>
  <div class="stage-content backend-stage">
    <div class="section-title">数据模型</div>
    <div
      v-for="m in data.data_models"
      :key="m.name"
      class="model-card"
    >
      <div class="model-name" @click="toggleModel(m.name)">
        {{ m.name }}
        <span class="expand-icon">{{ expandedModels.has(m.name) ? '▲' : '▼' }}</span>
      </div>
      <div v-if="expandedModels.has(m.name)" class="model-fields">
        <div v-for="f in m.fields" :key="f.name" class="field-row">
          <span class="field-name">{{ f.name }}</span>
          <span class="field-type">{{ f.type }}</span>
          <span class="field-desc">{{ f.description }}</span>
        </div>
      </div>
    </div>

    <div class="section-title">API 接口</div>
    <div class="endpoints-table">
      <div
        v-for="e in data.endpoints"
        :key="e.method + e.path"
        class="endpoint-row"
      >
        <span class="method-badge" :class="e.method.toLowerCase()">{{ e.method }}</span>
        <span class="endpoint-path">{{ e.path }}</span>
        <span class="endpoint-desc">{{ e.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
defineProps({ data: Object, extra: Object })
const expandedModels = ref(new Set())
const toggleModel = n => expandedModels.value.has(n) ? expandedModels.value.delete(n) : expandedModels.value.add(n)
</script>

<template>
  <div class="stage-content pm-stage">
    <p class="overview">{{ data.overview }}</p>
    <div class="features-list">
      <div
        v-for="f in data.features"
        :key="f.id"
        class="feature-item"
        :class="{ expanded: expanded.has(f.id) }"
      >
        <div class="feature-header" @click="toggle(f.id)">
          <span class="feature-id">{{ f.id }}</span>
          <span class="feature-name">{{ f.name }}</span>
          <span class="expand-icon">{{ expanded.has(f.id) ? '▲' : '▼' }}</span>
        </div>
        <div v-if="expanded.has(f.id)" class="feature-detail">
          <p class="feature-desc">{{ f.description }}</p>
          <div class="criteria-list">
            <div
              v-for="(c, i) in f.acceptance_criteria"
              :key="i"
              class="criterion"
            >
              <span class="check">✓</span> {{ c }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
defineProps({ data: Object, extra: Object })
const expanded = ref(new Set())
const toggle = id => expanded.value.has(id) ? expanded.value.delete(id) : expanded.value.add(id)
</script>

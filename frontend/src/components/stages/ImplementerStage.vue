<template>
  <div class="stage-content impl-stage">
    <div v-if="extra.progress" class="progress-row">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
      </div>
      <span class="progress-label">{{ extra.progress }}</span>
    </div>

    <div v-if="extra.module" class="current-module">
      当前模块：<strong>{{ extra.module }}</strong>
    </div>

    <div class="files-list">
      <div
        v-for="(f, i) in files"
        :key="i"
        class="file-row"
        :class="fileClass(f)"
      >
        <span class="file-icon">{{ fileIcon(f) }}</span>
        <span class="file-path">{{ f }}</span>
      </div>
    </div>

    <div v-if="extra.remaining === 0" class="all-done">
      ✓ 所有模块实现完毕
    </div>
    <div v-else-if="extra.remaining > 0" class="remaining-hint">
      还剩 {{ extra.remaining }} 个模块
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ data: Object, extra: Object })

const files = computed(() => {
  const f = props.data?.files
  if (Array.isArray(f)) return f
  if (props.data?.path) return [`[创建] ${props.data.path}`]
  return []
})

const progressPct = computed(() => {
  const p = props.extra?.progress
  if (!p) return 0
  const [cur, total] = p.split('/').map(Number)
  return Math.round((cur / total) * 100)
})

const fileClass = f => {
  if (f.includes('[创建]')) return 'create'
  if (f.includes('[修改]')) return 'edit'
  if (f.includes('[删除]')) return 'delete'
  if (f.includes('[失败]')) return 'fail'
  return 'create'
}
const fileIcon = f => {
  if (f.includes('[创建]') || f.includes('创建')) return '+'
  if (f.includes('[修改]') || f.includes('修改')) return '~'
  if (f.includes('[删除]') || f.includes('删除')) return '−'
  return '+'
}
</script>

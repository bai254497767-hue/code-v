<template>
  <div class="stage-card" :class="[msg.stage, msg.status]">
    <div class="card-header">
      <span class="stage-emoji">{{ msg.emoji }}</span>
      <span class="stage-title">{{ msg.title }}</span>
      <span class="card-badge" :class="msg.status">{{ badgeText }}</span>
    </div>

    <div class="card-body">
      <component :is="stageComp" :data="msg.data" :extra="msg.extra" :project-state="projectState" />
    </div>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent } from 'vue'

const props = defineProps({
  msg: Object,
  projectState: { type: Object, default: () => ({}) },
})

// 动态加载各阶段子组件
const stageComponents = {
  ceo:         defineAsyncComponent(() => import('./stages/CeoStage.vue')),
  pm:          defineAsyncComponent(() => import('./stages/PmStage.vue')),
  cto:         defineAsyncComponent(() => import('./stages/CtoStage.vue')),
  backend:     defineAsyncComponent(() => import('./stages/BackendStage.vue')),
  frontend:    defineAsyncComponent(() => import('./stages/FrontendStage.vue')),
  implementer: defineAsyncComponent(() => import('./stages/ImplementerStage.vue')),
  fixer:       defineAsyncComponent(() => import('./stages/FixerStage.vue')),
  tester:      defineAsyncComponent(() => import('./stages/TesterStage.vue')),
  acceptance:  defineAsyncComponent(() => import('./stages/AcceptanceStage.vue')),
}

const stageComp = computed(() => stageComponents[props.msg.stage])

const BADGE = { waiting: '⏸ 等待决策', done: '✓ 完成', retrying: '↺ 重跑中', running: '⟳ 运行中' }
const badgeText = computed(() => BADGE[props.msg.status] || props.msg.status)
</script>

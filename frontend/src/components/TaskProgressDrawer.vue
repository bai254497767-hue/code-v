<template>
  <div class="drawer-backdrop" @click.self="$emit('close')">
    <aside class="side-drawer" aria-label="任务进度">
      <div class="drawer-header">
        <div>
          <div class="drawer-kicker">任务进度</div>
          <h2>{{ context?.project?.title || '当前任务' }}</h2>
        </div>
        <button class="drawer-close" type="button" @click="$emit('close')">×</button>
      </div>

      <div class="drawer-body">
        <section class="task-overview">
          <div class="task-overview-row">
            <span>整体进度</span>
            <strong>{{ progress.percent }}%</strong>
          </div>
          <div class="progress-bar large">
            <div class="progress-fill" :style="{ width: progress.percent + '%' }"></div>
          </div>
          <div class="task-current">{{ progress.current_label }}</div>
        </section>

        <section class="drawer-section">
          <div class="drawer-section-title">主流程</div>
          <div class="stage-timeline">
            <div
              v-for="stage in stages"
              :key="stage.id"
              class="stage-step"
              :class="stage.status"
            >
              <span class="stage-step-dot"></span>
              <div class="stage-step-main">
                <div class="stage-step-title">
                  <span>{{ stage.label }}</span>
                  <strong>{{ stageStatusLabel(stage.status) }}</strong>
                </div>
                <p>{{ stage.summary }}</p>
              </div>
            </div>
          </div>
        </section>

        <section class="drawer-section">
          <div class="drawer-section-title">PM 子任务</div>
          <div v-if="subtasks.length" class="subtask-list">
            <div
              v-for="task in subtasks"
              :key="task.id"
              class="subtask-item"
              :class="task.status"
            >
              <div class="subtask-head">
                <span class="subtask-id">{{ task.source_feature_id || task.id }}</span>
                <strong>{{ task.title }}</strong>
                <span class="subtask-status">{{ subtaskStatusLabel(task.status) }}</span>
              </div>
              <p v-if="task.description">{{ task.description }}</p>
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: (task.progress || 0) + '%' }"></div>
              </div>
            </div>
          </div>
          <div v-else class="drawer-empty">
            产品经理完成拆解后，这里会显示子任务。
          </div>
        </section>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  taskContext: { type: Object, default: null },
})
defineEmits(['close'])

const stageOrder = ['ceo', 'pm', 'cto', 'backend', 'frontend', 'implementer', 'tester', 'acceptance']

const context = computed(() => props.taskContext || {})
const progress = computed(() => context.value.progress || { percent: 0, current_label: '等待开始' })
const stages = computed(() => {
  const source = context.value.stages || {}
  return stageOrder.map(id => source[id]).filter(Boolean)
})
const subtasks = computed(() => context.value.subtasks || [])

function stageStatusLabel(status) {
  const labels = {
    pending: '未开始',
    running: '处理中',
    waiting: '待确认',
    done: '完成',
    error: '异常',
  }
  return labels[status] || status || '未开始'
}

function subtaskStatusLabel(status) {
  const labels = {
    pending: '未开始',
    running: '处理中',
    waiting: '待确认',
    done: '完成',
    failed: '失败',
  }
  return labels[status] || status || '未开始'
}
</script>

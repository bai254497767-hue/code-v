<template>
  <div class="project-list">
    <button class="new-btn" @click="showModal = true">
      <span>＋</span> 新建项目
    </button>

    <div class="list-label">项目列表</div>

    <div v-if="store.projects.length === 0" class="empty-hint">
      暂无项目，点击上方新建
    </div>

    <ul class="list">
      <li
        v-for="p in store.projects"
        :key="p.id"
        class="list-item"
        :class="{ active: store.currentId === p.id }"
        @click="store.selectProject(p.id)"
      >
        <span class="status-dot" :class="p.status"></span>
        <div class="item-info">
          <div class="item-name">{{ p.name || p.id }}</div>
          <div class="item-meta">
            <span class="stage-badge">{{ stageLabel(p.stage) }}</span>
            <span class="status-text" :class="p.status">{{ statusLabel(p.status) }}</span>
          </div>
        </div>
        <div class="item-actions">
          <button
            class="more-btn"
            type="button"
            title="更多操作"
            aria-label="更多操作"
            @click.stop="toggleMenu(p.id)"
          >
            ...
          </button>
          <div v-if="openMenuId === p.id" class="project-menu" @click.stop>
            <button type="button" @click="renameProject(p)">修改名称</button>
            <button type="button" class="danger" @click="deleteProject(p)">删除会话</button>
          </div>
        </div>
      </li>
    </ul>

    <NewProjectModal v-if="showModal" @close="showModal = false" @created="onCreated" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useProjectStore } from '../stores/project.js'
import NewProjectModal from './NewProjectModal.vue'

const store     = useProjectStore()
const showModal = ref(false)
const openMenuId = ref(null)

const STAGE_LABELS = {
  start: '待开始', ceo: '立项中', pm: '拆解中', cto: '技术规划',
  backend: '接口设计', frontend: '页面设计', implementer: '编码中',
  tester: '测试中', acceptance: '验收', done: '已完成',
}
const STATUS_LABELS = {
  new: '新建', planning: '规划中', designing: '设计中',
  coding: '编码中', testing: '测试中', running: '运行中', done: '已完成',
}

const stageLabel  = s => STAGE_LABELS[s] || s
const statusLabel = s => STATUS_LABELS[s] || s

function toggleMenu(projectId) {
  openMenuId.value = openMenuId.value === projectId ? null : projectId
}

async function renameProject(project) {
  openMenuId.value = null
  const currentName = project.name || project.id
  const nextName = window.prompt('请输入新的项目名称', currentName)
  const trimmed = (nextName || '').trim()
  if (!trimmed || trimmed === currentName) return

  try {
    await store.renameProject(project.id, trimmed)
  } catch (err) {
    window.alert(err.message || '修改名称失败')
  }
}

async function deleteProject(project) {
  openMenuId.value = null
  const name = project.name || project.id
  const confirmed = window.confirm(`确定删除「${name}」吗？这会同时删除数据库里的会话记录。`)
  if (!confirmed) return

  try {
    await store.deleteProject(project.id)
  } catch (err) {
    window.alert(err.message || '删除会话失败')
  }
}

async function onCreated(projectId) {
  showModal.value = false
  await store.fetchProjects()
  await store.selectProject(projectId)
}
</script>

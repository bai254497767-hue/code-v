<template>
  <div class="app-layout">
    <!-- 左侧项目列表 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <span class="logo">AI</span>
        <span class="logo-text">AI 软件工厂</span>
      </div>
      <ProjectList />
    </aside>

    <!-- 右侧对话区 -->
    <main class="main">
      <ChatArea />
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useProjectStore } from './stores/project.js'
import ProjectList from './components/ProjectList.vue'
import ChatArea from './components/ChatArea.vue'

const store = useProjectStore()
onMounted(() => store.fetchProjects())
</script>

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const API = ''  // 同域，通过 vite proxy 转发

export const useProjectStore = defineStore('project', () => {
  // ── 状态 ────────────────────────────────────────────────────────────────────
  const projects        = ref([])          // [{id, name, status, stage}]
  const currentId       = ref(null)        // 当前选中的项目 ID
  const messages        = ref([])          // 当前项目的对话消息列表
  const wsStatus        = ref('idle')      // 'idle'|'connecting'|'running'|'waiting'|'done'|'error'
  const pendingInterrupt = ref(null)       // 当前等待决策的 payload
  const currentStage    = ref(null)        // 当前正在运行的阶段名
  const stateSnapshot   = ref({})          // 当前项目最新状态快照
  const taskContext     = ref(null)        // 后端持久化的当前任务上下文
  const chatMessages    = ref([])          // 常驻聊天与过程摘要
  const feedbackQueue   = ref([])          // 待调度意见队列
  const errorMsg        = ref('')
  const llmProviders    = ref([])
  const defaultProvider = ref('codex')

  let eventSource = null
  let msgIdCounter = 0
  let chatIdCounter = 0

  // ── 计算属性 ──────────────────────────────────────────────────────────────
  const currentProject = computed(() =>
    projects.value.find(p => p.id === currentId.value) || null
  )

  // ── HTTP API ──────────────────────────────────────────────────────────────

  async function fetchProjects() {
    try {
      const res = await fetch(`${API}/api/projects`)
      const data = await res.json()
      projects.value = data.projects || []
    } catch (e) {
      console.error('fetchProjects', e)
    }
  }

  async function fetchLlmProviders() {
    try {
      const res = await fetch(`${API}/api/llm-providers`)
      const data = await res.json()
      llmProviders.value = data.providers || []
      defaultProvider.value = data.default_provider || 'codex'
    } catch (e) {
      console.error('fetchLlmProviders', e)
      llmProviders.value = [
        {
          id: 'codex',
          name: 'Codex 套餐模型',
          description: '通过 Codex CLI 使用当前 ChatGPT/Codex 登录态，不需要 API Key。',
          supports_custom_model: true,
        },
      ]
    }
  }

  async function createProject(requirement, llm = {}) {
    const res = await fetch(`${API}/api/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requirement,
        llm_provider: llm.provider,
        llm_model: llm.model,
        llm_effort: llm.effort,
        llm_speed: llm.speed,
        project_dir: llm.projectDir,
      }),
    })
    const data = await res.json()
    await fetchProjects()
    return data.project_id
  }

  async function pickProjectFolder() {
    const res = await fetch(`${API}/api/project-folder/pick`, {
      method: 'POST',
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data.detail || data.error || '选择项目文件夹失败')
    }
    return data.project_dir
  }

  async function updateProjectModel(projectId, llm = {}) {
    const res = await fetch(`${API}/api/projects/${projectId}/llm`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        llm_provider: llm.provider,
        llm_model: llm.model,
        llm_effort: llm.effort,
        llm_speed: llm.speed,
      }),
    })

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || data.error || '模型配置保存失败')
    }

    const data = await res.json()
    const project = projects.value.find(p => p.id === projectId)
    if (project) {
      project.llm_provider = data.llm_provider
      project.llm_model = data.llm_model
      project.llm_effort = data.llm_effort
      project.llm_speed = data.llm_speed
    }
    return data
  }

  async function renameProject(id, name) {
    const res = await fetch(`${API}/api/projects/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data.error || data.detail || '修改名称失败')
    }
    await fetchProjects()
    return data
  }

  async function deleteProject(id) {
    const res = await fetch(`${API}/api/projects/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data.error || data.detail || '删除会话失败')
    }
    if (currentId.value === id) {
      closeEvents()
      currentId.value = null
      messages.value = []
      chatMessages.value = []
      feedbackQueue.value = []
      stateSnapshot.value = {}
      taskContext.value = null
    }
    await fetchProjects()
    return data
  }

  // ── 项目选择 & 历史消息恢复 ──────────────────────────────────────────────

  async function selectProject(id) {
    if (currentId.value === id) return
    // 关闭旧 SSE 连接
    closeEvents()
    currentId.value      = id
    messages.value       = []
    chatMessages.value   = []
    feedbackQueue.value  = []
    stateSnapshot.value  = {}
    taskContext.value    = null
    pendingInterrupt.value = null
    wsStatus.value       = 'connecting'
    errorMsg.value       = ''
    connectEvents(id)
  }

  // ── SSE 事件流 + HTTP 决策 ────────────────────────────────────────────────

  function connectEvents(projectId) {
    const eventsUrl = `${API}/api/projects/${encodeURIComponent(projectId)}/events`
    eventSource = new EventSource(eventsUrl)

    eventSource.onopen = () => {
      wsStatus.value = 'connecting'
    }

    eventSource.onmessage = (evt) => {
      const msg = JSON.parse(evt.data)
      handleMessage(msg, projectId)
    }

    eventSource.onerror = () => {
      if (wsStatus.value === 'done' || wsStatus.value === 'error') return
      wsStatus.value = 'connecting'
      errorMsg.value = '事件流连接中断，正在自动重连'
    }
  }

  function closeEvents() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    wsStatus.value     = 'idle'
    pendingInterrupt.value = null
    currentStage.value = null
  }

  function handleMessage(msg, projectId) {
    if (msg.task_context) {
      _applyTaskContext(msg.task_context)
    }

    if (msg.type === 'init') {
      // 恢复历史状态，重建消息列表
      wsStatus.value = 'running'
      stateSnapshot.value = msg.state || {}
      _applyTaskContext(msg.task_context || null)
      chatMessages.value = (msg.state?.chat_events || []).map(_normalizeChatMessage)
      feedbackQueue.value = msg.state?.feedback_queue || []
      _rebuildFromState(stateSnapshot.value)
      return
    }

    if (msg.type === 'interrupt') {
      wsStatus.value     = 'waiting'
      currentStage.value = msg.stage
      pendingInterrupt.value = msg
      _setStageState(msg.stage, msg.data)

      // 如果消息列表已有该阶段的卡片，更新它；否则新增
      const existing = messages.value.find(
        m => m.stage === msg.stage && ['running', 'waiting', 'retrying'].includes(m.status)
      )
      if (existing) {
        existing.status = 'waiting'
        existing.data   = msg.data
        existing.extra  = _extractExtra(msg)
      } else {
        messages.value.push({
          id:     ++msgIdCounter,
          stage:  msg.stage,
          emoji:  msg.emoji,
          title:  msg.title,
          data:   msg.data,
          extra:  _extractExtra(msg),
          status: 'waiting',
        })
      }

      // 更新项目列表状态
      const proj = projects.value.find(p => p.id === projectId)
      if (proj) proj.status = 'running'

      return
    }

    if (msg.type === 'running') {
      wsStatus.value     = 'running'
      currentStage.value = msg.stage
      if (msg.message) _appendChat('progress', msg.message, { stage: msg.stage })
      return
    }

    if (msg.type === 'user_feedback_queued') {
      feedbackQueue.value = msg.queue || (msg.item ? [...feedbackQueue.value, msg.item] : feedbackQueue.value)
      if (msg.item?.text) _appendChat('user', msg.item.text, { id: msg.item.id, ts: msg.item.ts })
      return
    }

    if (msg.type === 'dispatch_started') {
      wsStatus.value = 'running'
      _appendChat('dispatch', msg.message || 'CEO 正在判断调度目标')
      return
    }

    if (msg.type === 'dispatch_decision') {
      feedbackQueue.value = []
      _appendChat('dispatch', msg.message || 'CEO 已完成调度判断', { decision: msg.decision })
      return
    }

    if (msg.type === 'llm_progress') {
      wsStatus.value = 'running'
      currentStage.value = msg.stage || currentStage.value
      _appendChat('progress', msg.message, { stage: msg.stage, event: msg.event, ts: msg.ts })
      return
    }

    if (msg.type === 'interrupt_requested') {
      _appendChat('system', msg.message || '已请求打断')
      return
    }

    if (msg.type === 'complete') {
      wsStatus.value     = 'done'
      currentStage.value = null
      pendingInterrupt.value = null
      if (msg.state) stateSnapshot.value = msg.state
      _applyTaskContext(msg.task_context || taskContext.value)
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }

      // 把最后一条 waiting 卡片标为 done
      const last = [...messages.value].reverse().find(m => m.status === 'waiting')
      if (last) last.status = 'done'

      // 更新项目列表
      fetchProjects()
      return
    }

    if (msg.type === 'error') {
      wsStatus.value = 'error'
      errorMsg.value = msg.message || '未知错误'
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
      return
    }
  }

  function _extractExtra(msg) {
    const reserved = ['type', 'stage', 'emoji', 'title', 'data']
    const extra = {}
    for (const k of Object.keys(msg)) {
      if (!reserved.includes(k)) extra[k] = msg[k]
    }
    return extra
  }

  function _applyTaskContext(context) {
    if (!context) return
    taskContext.value = context
    if (context.project?.current_stage) {
      currentStage.value = context.project.current_stage
    }
    const project = projects.value.find(p => p.id === context.project?.id)
    if (project) {
      project.name = context.project.title || project.name
      project.status = context.project.status || project.status
      project.stage = context.project.current_stage || project.stage
      project.llm_provider = context.project.llm_provider || project.llm_provider
      project.llm_model = context.project.llm_model || project.llm_model
      project.llm_effort = context.project.llm_effort || project.llm_effort
      project.llm_speed = context.project.llm_speed || project.llm_speed
      project.project_dir = context.project.project_dir || project.project_dir
    }
  }

  function _rebuildFromState(state) {
    messages.value = []
    const stageOrder = ['ceo', 'pm', 'cto', 'backend', 'frontend', 'implementer', 'tester', 'acceptance']
    const stageMap = {
      ceo:         { key: 'brief',       emoji: '🏢', title: 'CEO — 项目立项' },
      pm:          { key: 'features',    emoji: '📋', title: '产品经理 — 功能拆解' },
      cto:         { key: 'tech_plan',   emoji: '🔧', title: 'CTO — 技术方案' },
      backend:     { key: 'api_spec',    emoji: '🗄️', title: '后端 — 数据结构 & 接口文档' },
      frontend:    { key: 'ui_spec',     emoji: '🎨', title: '前端 — 页面结构设计' },
      implementer: { key: 'code_files',  emoji: '💻', title: '代码实现' },
      tester:      { key: 'test_report', emoji: '🧪', title: 'QA — 测试报告' },
      acceptance:  { key: 'acceptance',  emoji: '✅', title: '产品验收' },
    }

    for (const stage of stageOrder) {
      const { key, emoji, title } = stageMap[stage]
      const val = state[key]
      // 跳过 null/undefined/空数组（code_files 初始化为 [] 不应触发卡片）
      const hasData = val !== null && val !== undefined &&
                      !(Array.isArray(val) && val.length === 0)
      if (hasData) {
        messages.value.push({
          id:     ++msgIdCounter,
          stage,
          emoji,
          title,
          data:   val,
          extra:  {},
          status: 'done',
        })
      }
    }
  }

  function _setStageState(stage, data) {
    const keyMap = {
      ceo: 'brief',
      pm: 'features',
      cto: 'tech_plan',
      backend: 'api_spec',
      frontend: 'ui_spec',
      implementer: 'code_files',
      tester: 'test_report',
      acceptance: 'acceptance',
    }
    const key = keyMap[stage]
    if (key) stateSnapshot.value = { ...stateSnapshot.value, [key]: data }
  }

  function _normalizeChatMessage(event) {
    return {
      id: event.id || `chat-${++chatIdCounter}`,
      kind: event.kind || 'system',
      text: event.text || event.message || '',
      stage: event.stage,
      ts: event.ts || Date.now() / 1000,
      decision: event.decision,
    }
  }

  function _appendChat(kind, text, extra = {}) {
    if (!text) return
    const id = extra.id || `chat-${++chatIdCounter}`
    if (chatMessages.value.some(m => m.id === id)) return
    chatMessages.value.push({
      id,
      kind,
      text,
      stage: extra.stage,
      event: extra.event,
      ts: extra.ts || Date.now() / 1000,
      decision: extra.decision,
    })
  }

  // ── 决策 ────────────────────────────────────────────────────────────────────

  async function sendDecision(action, feedback = '') {
    if (!currentId.value) return

    // 把当前 waiting 卡片标为 done 或 retrying
    const waitingCard = messages.value.find(m => m.status === 'waiting')
    if (waitingCard) {
      waitingCard.status = action === 'retry' ? 'retrying' : 'done'
    }

    pendingInterrupt.value = null
    wsStatus.value         = action === 'abort' ? 'done' : 'running'

    try {
      const res = await fetch(`${API}/api/projects/${encodeURIComponent(currentId.value)}/decisions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, feedback }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || data.error || '提交决策失败')
      }
    } catch (e) {
      wsStatus.value = 'error'
      errorMsg.value = e.message || '提交决策失败'
    }
  }

  async function submitChat(message) {
    const text = (message || '').trim()
    if (!text || !currentId.value) return
    const res = await fetch(`${API}/api/projects/${encodeURIComponent(currentId.value)}/decisions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'chat_submit', message: text }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.error || '提交意见失败')
    if (data.item) {
      feedbackQueue.value = feedbackQueue.value.some(item => item.id === data.item.id)
        ? feedbackQueue.value
        : [...feedbackQueue.value, data.item]
      if (data.item.text) _appendChat('user', data.item.text, { id: data.item.id, ts: data.item.ts })
    }
    return data
  }

  async function requestInterrupt(message = '') {
    const text = (message || '').trim()
    if (text) await submitChat(text)
    const res = await fetch(`${API}/api/projects/${encodeURIComponent(currentId.value)}/decisions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'request_interrupt' }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.error || '请求打断失败')
    return data
  }

  return {
    // state
    projects, currentId, messages, wsStatus,
    pendingInterrupt, currentStage, stateSnapshot,
    taskContext, chatMessages, feedbackQueue, errorMsg,
    llmProviders, defaultProvider,
    // computed
    currentProject,
    // actions
    fetchProjects, fetchLlmProviders, createProject, pickProjectFolder,
    updateProjectModel, renameProject, deleteProject, selectProject,
    connectEvents, closeEvents, sendDecision, submitChat, requestInterrupt,
  }
})

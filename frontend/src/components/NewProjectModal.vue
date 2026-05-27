<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h2>新建项目</h2>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="modal-body">
        <label class="field-label">模型</label>
        <div class="model-picker">
          <select v-model="selectedProvider" class="model-select">
            <option
              v-for="provider in providers"
              :key="provider.id"
              :value="provider.id"
            >
              {{ provider.name }}
            </option>
          </select>
          <select
            v-model="modelOverride"
            class="model-input"
          >
            <option
              v-for="option in currentModelOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </div>
        <div class="model-hint">{{ currentProvider?.description }}</div>

        <div class="model-tuning-grid">
          <label class="field-label compact">
            智能
            <select v-model="effortOverride" class="model-input">
              <option
                v-for="option in currentEffortOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </label>
          <label class="field-label compact">
            速度
            <select v-model="speedOverride" class="model-input">
              <option
                v-for="option in currentSpeedOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </label>
        </div>

        <label class="field-label">项目文件夹</label>
        <div class="folder-picker">
          <button
            type="button"
            class="folder-btn"
            :disabled="folderChoosing || loading"
            @click="chooseProjectFolder"
          >
            {{ folderChoosing ? '正在请求权限...' : '选择文件夹并授权' }}
          </button>
          <div class="folder-path" :class="{ empty: !projectDir }">
            {{ projectDir || '未选择项目文件夹' }}
          </div>
        </div>
        <div class="folder-hint">
          生成的项目文件会写入你选择并授权的本地文件夹。
        </div>
        <div v-if="folderError" class="folder-error">{{ folderError }}</div>

        <label class="field-label">产品需求描述</label>
        <textarea
          v-model="requirement"
          class="requirement-input"
          placeholder="描述你想要构建的产品，例如：做一个带用户认证的 Todo 应用，支持添加、删除、标记完成任务，数据存储在本地数据库..."
          rows="6"
          autofocus
        ></textarea>
        <div class="char-count">{{ requirement.length }} 字</div>
      </div>

      <div class="modal-footer">
        <button class="cancel-btn" @click="$emit('close')">取消</button>
        <button
          class="submit-btn"
          :disabled="!requirement.trim() || !projectDir || loading"
          @click="submit"
        >
          <span v-if="loading" class="spinner"></span>
          {{ loading ? '创建中...' : '🚀 开始构建' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useProjectStore } from '../stores/project.js'

const emit = defineEmits(['close', 'created'])
const store       = useProjectStore()
const requirement = ref('')
const loading     = ref(false)
const folderChoosing = ref(false)
const projectDir = ref('')
const folderError = ref('')
const selectedProvider = ref('codex')
const modelOverride = ref('')
const effortOverride = ref('')
const speedOverride = ref('')

const fallbackProviders = [
  {
    id: 'codex',
    name: 'Codex 套餐模型',
    description: '通过 Codex CLI 使用当前 ChatGPT/Codex 登录态，不需要 API Key。',
    supports_custom_model: true,
    default_model: 'gpt-5.5',
    default_effort: 'high',
    default_speed: 'standard',
    model_options: [
      { label: 'GPT-5.5', value: 'gpt-5.5' },
      { label: 'GPT-5.4', value: 'gpt-5.4' },
      { label: 'GPT-5.4-Mini', value: 'gpt-5.4-mini' },
      { label: 'GPT-5.3-Codex', value: 'gpt-5.3-codex' },
      { label: 'GPT-5.3-Codex-Spark', value: 'gpt-5.3-codex-spark' },
      { label: 'GPT-5.2', value: 'gpt-5.2' },
    ],
    effort_options: [
      { label: '低', value: 'low' },
      { label: '中', value: 'medium' },
      { label: '高', value: 'high' },
      { label: '超高', value: 'xhigh' },
    ],
    speed_options: [
      { label: '标准', value: 'standard' },
      { label: '快速', value: 'fast' },
    ],
  },
]

const providers = computed(() =>
  store.llmProviders.length ? store.llmProviders : fallbackProviders
)

const currentProvider = computed(() =>
  providers.value.find(p => p.id === selectedProvider.value) || providers.value[0]
)
const currentModelOptions = computed(() => currentProvider.value?.model_options || [])
const currentEffortOptions = computed(() => currentProvider.value?.effort_options || [])
const currentSpeedOptions = computed(() => currentProvider.value?.speed_options || [])

onMounted(async () => {
  await store.fetchLlmProviders()
  selectedProvider.value = store.defaultProvider || providers.value[0]?.id || 'codex'
  fillModelDefaults()
})

watch(providers, (items) => {
  if (!items.some(p => p.id === selectedProvider.value)) {
    selectedProvider.value = items[0]?.id || 'codex'
  }
  fillModelDefaults()
})

watch(selectedProvider, () => fillModelDefaults())

function fillModelDefaults() {
  const provider = currentProvider.value
  modelOverride.value = provider?.default_model || provider?.model_options?.[0]?.value || ''
  effortOverride.value = provider?.default_effort || provider?.effort_options?.[0]?.value || ''
  speedOverride.value = provider?.default_speed || provider?.speed_options?.[0]?.value || 'standard'
}

async function chooseProjectFolder() {
  folderChoosing.value = true
  folderError.value = ''
  try {
    projectDir.value = await store.pickProjectFolder()
  } catch (e) {
    folderError.value = e.message || '选择项目文件夹失败'
  } finally {
    folderChoosing.value = false
  }
}

async function submit() {
  if (!requirement.value.trim() || !projectDir.value) return
  loading.value = true
  try {
    const id = await store.createProject(requirement.value.trim(), {
      provider: selectedProvider.value,
      model: modelOverride.value || null,
      effort: effortOverride.value || null,
      speed: speedOverride.value || null,
      projectDir: projectDir.value,
    })
    emit('created', id)
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}
</script>

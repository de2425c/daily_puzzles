<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import api from '../api'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  slot: {
    type: Object,
    required: true
  },
  config: {
    type: Object,
    required: true
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['select', 'close'])

// State
const loadingTree = ref(false)
const error = ref(null)
const currentPath = ref('r:0')
const pathHistory = ref([{ path: 'r:0', label: 'Start' }])
const currentNode = ref(null)
const ranges = ref(null)

// Card selection
const cardInput = ref('')
const showCardInput = ref(false)

// Get parent slot's sim
const parentSlot = computed(() => {
  return props.config.slots.find(s => s.id === props.slot.parent_slot_id)
})

const parentSimId = computed(() => parentSlot.value?.sim_id)

const isTerminal = computed(() => currentNode.value?.is_terminal || false)

const cardLabel = computed(() => {
  if (props.slot.street === 'turn') return 'Turn Card'
  return 'River Card'
})

async function loadNode(path) {
  if (!parentSimId.value) return

  loadingTree.value = true
  error.value = null

  try {
    currentNode.value = await api.getTreeActions(parentSimId.value, path)
    ranges.value = await api.getTreeRanges(parentSimId.value, path)
    currentPath.value = path

    // If terminal, show card input
    if (currentNode.value.is_terminal) {
      showCardInput.value = true
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loadingTree.value = false
  }
}

function selectAction(action) {
  pathHistory.value.push({ path: action.path, label: action.label })
  loadNode(action.path)
}

function goBack() {
  if (pathHistory.value.length <= 1) return
  pathHistory.value.pop()
  const prevPath = pathHistory.value[pathHistory.value.length - 1].path
  loadNode(prevPath)
  showCardInput.value = false
}

function formatFrequency(freq) {
  if (freq === undefined || freq === null) return ''
  return `${(freq * 100).toFixed(0)}%`
}

function confirmSelection() {
  const card = cardInput.value.trim() || null
  emit('select', currentPath.value, card)
}

onMounted(() => {
  if (parentSimId.value) {
    loadNode('r:0')
  }
})

watch(() => props.visible, (visible) => {
  if (visible && parentSimId.value) {
    currentPath.value = 'r:0'
    pathHistory.value = [{ path: 'r:0', label: 'Start' }]
    showCardInput.value = false
    cardInput.value = ''
    loadNode('r:0')
  }
})
</script>

<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Select Action Path to {{ slot.street }}</h2>
        <button class="close-btn" @click="$emit('close')" :disabled="loading">&times;</button>
      </div>

      <div class="modal-body">
        <div v-if="error" class="error">{{ error }}</div>

        <!-- Path breadcrumb -->
        <div class="path-breadcrumb">
          <span
            v-for="(item, idx) in pathHistory"
            :key="item.path"
            class="breadcrumb-item"
          >
            <span v-if="idx > 0" class="separator">&rarr;</span>
            <span class="crumb">{{ item.label }}</span>
          </span>
        </div>

        <!-- Range info -->
        <div v-if="ranges && !loadingTree" class="range-info">
          <div class="range-stat">
            <span class="label">{{ config.ip_position }} (IP)</span>
            <span class="value">{{ ranges.ip_combos }} combos</span>
          </div>
          <div class="range-stat">
            <span class="label">{{ config.oop_position }} (OOP)</span>
            <span class="value">{{ ranges.oop_combos }} combos</span>
          </div>
          <div class="range-stat">
            <span class="label">Pot</span>
            <span class="value">{{ ranges.pot_size_bb?.toFixed(1) }}bb</span>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="loadingTree" class="loading">Loading tree...</div>

        <!-- Action buttons -->
        <div v-else-if="!isTerminal && currentNode?.actions" class="action-buttons">
          <div class="action-prompt">
            <span class="position-label">{{ currentNode.position }} to act</span>
          </div>
          <div class="actions-grid">
            <button
              v-for="action in currentNode.actions"
              :key="action.path"
              class="action-btn"
              @click="selectAction(action)"
              :disabled="loading"
            >
              {{ action.label }}
            </button>
          </div>
        </div>

        <!-- Terminal: card input -->
        <div v-else-if="showCardInput" class="card-input-section">
          <div class="terminal-message">
            Action complete at this node. Select {{ cardLabel.toLowerCase() }}.
          </div>
          <div class="card-input">
            <label>{{ cardLabel }} (leave empty for random)</label>
            <input
              type="text"
              v-model="cardInput"
              placeholder="e.g., 8h"
              maxlength="2"
              :disabled="loading"
            />
          </div>
        </div>

        <!-- Back button -->
        <div v-if="pathHistory.length > 1" class="back-row">
          <button class="back-btn" @click="goBack" :disabled="loading || loadingTree">
            &larr; Go Back
          </button>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" @click="$emit('close')" :disabled="loading">
          Cancel
        </button>
        <button
          v-if="isTerminal"
          class="btn-primary"
          @click="confirmSelection"
          :disabled="loading"
        >
          {{ loading ? 'Creating Sim...' : `Create ${slot.street} Sim` }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 100%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
  position: sticky;
  top: 0;
  background: white;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #999;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover:not(:disabled) {
  color: #333;
}

.modal-body {
  padding: 20px;
}

.error {
  background: #ffebee;
  color: #c62828;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;
}

.path-breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
}

.separator {
  color: #999;
  margin: 0 4px;
}

.crumb {
  color: #333;
}

.range-info {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}

.range-stat {
  background: #f8f9fa;
  padding: 8px 12px;
  border-radius: 6px;
  text-align: center;
}

.range-stat .label {
  display: block;
  font-size: 11px;
  color: #666;
}

.range-stat .value {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.loading {
  text-align: center;
  color: #666;
  padding: 20px;
}

.action-buttons {
  margin-bottom: 16px;
}

.action-prompt {
  margin-bottom: 12px;
}

.position-label {
  font-size: 14px;
  font-weight: 600;
  color: #1976d2;
}

.actions-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.action-btn {
  padding: 10px 16px;
  border: 2px solid #e0e0e0;
  background: #fff;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  border-color: #1976d2;
  background: #e3f2fd;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.card-input-section {
  margin-bottom: 16px;
}

.terminal-message {
  background: #e8f5e9;
  color: #2e7d32;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
}

.card-input label {
  display: block;
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.card-input input {
  width: 100%;
  max-width: 100px;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 18px;
  font-family: monospace;
  text-transform: uppercase;
}

.card-input input:focus {
  outline: none;
  border-color: #1976d2;
}

.back-row {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.back-btn {
  padding: 8px 16px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.back-btn:hover:not(:disabled) {
  background: #e9ecef;
}

.back-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
  position: sticky;
  bottom: 0;
  background: white;
}

.btn-primary,
.btn-secondary {
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #1976d2;
  color: white;
  border: none;
}

.btn-primary:hover:not(:disabled) {
  background: #1565c0;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  color: #666;
  border: 1px solid #ddd;
}

.btn-secondary:hover:not(:disabled) {
  background: #f5f5f5;
}
</style>

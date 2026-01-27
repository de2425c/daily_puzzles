<script setup>
import { ref, computed } from 'vue'
import api from '../api'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['select'])

// State
const loading = ref(false)
const error = ref(null)
const positions = ref([])
const selectedPath = ref([])
const currentNode = ref(null)
const availableResponses = ref([])
const scenarioSummary = ref(null)

// Computed
const isComplete = computed(() => scenarioSummary.value !== null)

const actionHistory = computed(() => {
  return selectedPath.value.map(name => {
    const parts = name.split('_')
    const pos = parts[0]
    const action = parts.slice(1).join('_')
    return { position: pos, action: formatAction(action), name }
  })
})

function formatAction(action) {
  if (action === 'RFI') return 'opens'
  if (action === '3B') return '3-bets'
  if (action === '4B') return '4-bets'
  if (action === '5B') return '5-bets'
  if (action === 'Call') return 'calls'
  return action
}

async function loadPositions() {
  try {
    positions.value = await api.getPreflopPositions()
  } catch (e) {
    error.value = 'Failed to load positions: ' + e.message
  }
}

async function selectOpener(position) {
  loading.value = true
  error.value = null
  scenarioSummary.value = null

  try {
    const rfiName = `${position}_RFI`
    const node = await api.getPreflopRfiNode(position)
    selectedPath.value = [rfiName]
    currentNode.value = node

    const children = await api.getPreflopChildren([rfiName])
    availableResponses.value = children
  } catch (e) {
    error.value = 'Failed to load opener data: ' + e.message
  } finally {
    loading.value = false
  }
}

async function selectResponse(response) {
  loading.value = true
  error.value = null

  try {
    const newPath = [...selectedPath.value, response.name]
    selectedPath.value = newPath

    const node = await api.getPreflopNode(newPath)
    currentNode.value = node

    if (response.action === 'Call' || node.children.length === 0) {
      await loadScenarioSummary()
    } else {
      const children = await api.getPreflopChildren(newPath)
      availableResponses.value = children
    }
  } catch (e) {
    error.value = 'Failed to load response: ' + e.message
  } finally {
    loading.value = false
  }
}

async function loadScenarioSummary() {
  try {
    scenarioSummary.value = await api.getPreflopScenario(selectedPath.value)
    availableResponses.value = []
  } catch (e) {
    error.value = 'Failed to load scenario summary: ' + e.message
  }
}

function reset() {
  selectedPath.value = []
  currentNode.value = null
  availableResponses.value = []
  scenarioSummary.value = null
  error.value = null
}

function confirmSelection() {
  emit('select', selectedPath.value)
}

function getResponseLabel(response) {
  const pos = response.name.split('_')[0]
  const action = response.action === 'Raise' ?
    (response.size ? `raises to ${response.size}bb` : 'raises') :
    'calls'
  return `${pos} ${action}`
}

loadPositions()
</script>

<template>
  <div class="preflop-config-selector">
    <div v-if="error" class="error">{{ error }}</div>

    <!-- Step 1: Select Opener -->
    <div class="step" v-if="selectedPath.length === 0">
      <h3>Select Opener Position</h3>
      <div class="position-buttons">
        <button
          v-for="pos in positions"
          :key="pos"
          @click="selectOpener(pos)"
          class="position-btn"
          :disabled="loading || disabled"
        >
          {{ pos }}
        </button>
      </div>
    </div>

    <!-- Action History -->
    <div class="action-history" v-if="actionHistory.length > 0">
      <div class="action-step" v-for="(action, i) in actionHistory" :key="i">
        <span class="step-number">{{ i + 1 }}.</span>
        <span class="position">{{ action.position }}</span>
        <span class="action">{{ action.action }}</span>
      </div>
    </div>

    <!-- Available Responses -->
    <div class="step" v-if="availableResponses.length > 0 && !isComplete">
      <h3>Select Response</h3>
      <div class="response-buttons">
        <button
          v-for="resp in availableResponses"
          :key="resp.name"
          @click="selectResponse(resp)"
          class="response-btn"
          :disabled="loading || disabled"
        >
          {{ getResponseLabel(resp) }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading">Loading...</div>

    <!-- Scenario Summary -->
    <div class="scenario-summary" v-if="isComplete && scenarioSummary">
      <h3>Scenario Ready</h3>
      <div class="summary-description">{{ scenarioSummary.preflop_description }}</div>

      <div class="summary-grid">
        <div class="summary-item">
          <span class="label">{{ scenarioSummary.ip_position }} (IP)</span>
          <span class="value">{{ scenarioSummary.ip_combos }} combos</span>
        </div>
        <div class="summary-item">
          <span class="label">{{ scenarioSummary.oop_position }} (OOP)</span>
          <span class="value">{{ scenarioSummary.oop_combos }} combos</span>
        </div>
        <div class="summary-item">
          <span class="label">Pot</span>
          <span class="value">{{ scenarioSummary.pot_size_bb }}bb</span>
        </div>
        <div class="summary-item">
          <span class="label">Stacks</span>
          <span class="value">{{ scenarioSummary.effective_stack_bb.toFixed(1) }}bb</span>
        </div>
      </div>

      <div class="actions">
        <button @click="reset" class="btn-secondary" :disabled="disabled">
          Start Over
        </button>
        <button @click="confirmSelection" class="btn-primary" :disabled="disabled">
          Use This Scenario
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.preflop-config-selector {
  padding: 16px 0;
}

.error {
  background: #ffebee;
  color: #c62828;
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 16px;
}

.step {
  margin-bottom: 20px;
}

.step h3 {
  font-size: 14px;
  font-weight: 600;
  color: #666;
  margin: 0 0 12px 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.position-buttons,
.response-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.position-btn,
.response-btn {
  padding: 10px 20px;
  border: 2px solid #e0e0e0;
  background: #fff;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.position-btn:hover:not(:disabled),
.response-btn:hover:not(:disabled) {
  border-color: #1976d2;
  background: #e3f2fd;
}

.position-btn:disabled,
.response-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-history {
  background: #f5f5f5;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 20px;
}

.action-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.step-number {
  color: #999;
  font-size: 12px;
  width: 20px;
}

.action-step .position {
  font-weight: 600;
  color: #333;
}

.action-step .action {
  color: #666;
}

.loading {
  color: #666;
  font-style: italic;
  padding: 12px 0;
}

.scenario-summary {
  border-top: 1px solid #eee;
  padding-top: 20px;
}

.scenario-summary h3 {
  font-size: 16px;
  margin: 0 0 8px 0;
  color: #333;
}

.summary-description {
  color: #666;
  margin-bottom: 16px;
  font-size: 14px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.summary-item {
  background: #f8f9fa;
  padding: 12px;
  border-radius: 6px;
  text-align: center;
}

.summary-item .label {
  display: block;
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}

.summary-item .value {
  display: block;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.actions {
  display: flex;
  gap: 12px;
}

.btn-primary,
.btn-secondary {
  padding: 12px 24px;
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

@media (max-width: 600px) {
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>

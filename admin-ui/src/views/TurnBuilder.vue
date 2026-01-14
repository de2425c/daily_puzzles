<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute()
const router = useRouter()

// State
const sim = ref(null)
const loading = ref(true)
const error = ref(null)
const creating = ref(false)

// Action path building
const actionHistory = ref([])  // { label: string, path: string }[]
const currentNode = ref(null)  // Current node info from API
const rangesInfo = ref(null)   // Ranges at current terminal node

// Turn card input
const turnCard = ref('')
const iterations = ref(500)

// Computed
const currentPath = computed(() => {
  if (actionHistory.value.length === 0) return 'r:0'
  return actionHistory.value[actionHistory.value.length - 1].path
})

const isTerminal = computed(() => currentNode.value?.is_terminal ?? false)

const canCreate = computed(() => isTerminal.value && rangesInfo.value)

onMounted(async () => {
  try {
    sim.value = await api.getSim(route.params.id)
    // Load root node
    await loadNode('r:0')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function loadNode(path) {
  try {
    currentNode.value = await api.getTreeActions(sim.value.id, path)

    // If terminal, also load ranges
    if (currentNode.value.is_terminal) {
      rangesInfo.value = await api.getTreeRanges(sim.value.id, path)
    } else {
      rangesInfo.value = null
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

async function selectAction(action) {
  actionHistory.value.push({ label: action.label, path: action.path })
  await loadNode(action.path)
}

async function undoLastAction() {
  if (actionHistory.value.length > 0) {
    actionHistory.value.pop()
    const path = currentPath.value
    await loadNode(path)
  }
}

function resetActions() {
  actionHistory.value = []
  loadNode('r:0')
}

async function createTurnSim() {
  if (!canCreate.value) return

  creating.value = true
  error.value = null

  try {
    const result = await api.createTurnSim(
      sim.value.id,
      currentPath.value,
      turnCard.value || null,
      iterations.value
    )
    // Navigate to the new sim
    router.push(`/sims/${result.sim_id}`)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    creating.value = false
  }
}

function goBack() {
  router.push(`/sims/${sim.value.id}`)
}
</script>

<template>
  <div class="turn-builder">
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error && !sim" class="error">{{ error }}</div>
    <template v-else-if="sim">
      <!-- Header -->
      <div class="header card">
        <h2>Build Turn Line</h2>
        <div class="board-display">
          <span v-for="(card, i) in sim.board.match(/.{2}/g)" :key="i" class="card-chip">
            {{ card }}
          </span>
        </div>
        <div class="scenario">{{ sim.scenario.replace(/_/g, ' ').toUpperCase() }}</div>
        <div class="positions">{{ sim.ip_position }} (IP) vs {{ sim.oop_position }} (OOP)</div>
      </div>

      <!-- Action History -->
      <div class="card">
        <h3>Flop Action</h3>
        <div v-if="actionHistory.length === 0" class="no-actions">
          No actions selected yet
        </div>
        <div v-else class="action-history">
          <div v-for="(action, i) in actionHistory" :key="i" class="history-item">
            <span class="action-index">{{ i + 1 }}.</span>
            <span class="action-label">{{ action.label }}</span>
          </div>
        </div>
        <div class="history-controls">
          <button v-if="actionHistory.length > 0" @click="undoLastAction" class="small">
            Undo
          </button>
          <button v-if="actionHistory.length > 0" @click="resetActions" class="small">
            Reset
          </button>
        </div>
      </div>

      <!-- Current Decision -->
      <div v-if="!isTerminal && currentNode" class="card">
        <h3>{{ currentNode.position }} to Act</h3>
        <div class="action-buttons">
          <button
            v-for="action in currentNode.actions"
            :key="action.path"
            @click="selectAction(action)"
            class="action-btn"
          >
            {{ action.label }}
          </button>
        </div>
      </div>

      <!-- Terminal - Show Ranges -->
      <div v-if="isTerminal && rangesInfo" class="card terminal">
        <h3>Flop Action Closed</h3>
        <div class="ranges-display">
          <div class="range-info">
            <label>{{ sim.ip_position }} (IP)</label>
            <span class="combo-count">{{ rangesInfo.ip_combos }} combos</span>
          </div>
          <div class="range-info">
            <label>{{ sim.oop_position }} (OOP)</label>
            <span class="combo-count">{{ rangesInfo.oop_combos }} combos</span>
          </div>
          <div class="range-info">
            <label>Pot Size</label>
            <span>{{ rangesInfo.pot_size_bb.toFixed(1) }}bb</span>
          </div>
        </div>

        <!-- Turn Card Input -->
        <div class="turn-input">
          <label>Turn Card (optional, leave blank for random)</label>
          <input
            v-model="turnCard"
            placeholder="e.g., 8h"
            maxlength="2"
            class="turn-card-input"
          />
        </div>

        <!-- Iterations -->
        <div class="iterations-input">
          <label>Iterations</label>
          <select v-model="iterations">
            <option :value="250">250 (fast)</option>
            <option :value="500">500 (default)</option>
            <option :value="1000">1000 (accurate)</option>
          </select>
        </div>
      </div>

      <!-- Error -->
      <div v-if="error" class="error card">{{ error }}</div>

      <!-- Actions -->
      <div class="bottom-actions">
        <button
          v-if="canCreate"
          class="primary create-btn"
          @click="createTurnSim"
          :disabled="creating"
        >
          {{ creating ? 'Creating Turn Sim...' : 'Create Turn Sim (~$2)' }}
        </button>
        <button @click="goBack">Cancel</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.header {
  text-align: center;
}

h2 {
  margin-top: 0;
  margin-bottom: 16px;
}

.board-display {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 16px;
}

.card-chip {
  font-family: monospace;
  font-size: 24px;
  font-weight: bold;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 2px solid #dee2e6;
}

.scenario {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.positions {
  color: #666;
}

h3 {
  margin-top: 0;
  margin-bottom: 16px;
}

.no-actions {
  color: #999;
  font-style: italic;
}

.action-history {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.history-item {
  background: #e3f2fd;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 14px;
}

.action-index {
  color: #666;
  margin-right: 4px;
}

.action-label {
  font-weight: 500;
}

.history-controls {
  display: flex;
  gap: 8px;
}

.history-controls button.small {
  padding: 6px 12px;
  font-size: 12px;
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.action-btn {
  padding: 16px 24px;
  font-size: 16px;
  font-weight: 500;
  background: #f8f9fa;
  border: 2px solid #dee2e6;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #e3f2fd;
  border-color: #1976d2;
}

.terminal {
  background: #f1f8e9;
  border-color: #8bc34a;
}

.ranges-display {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.range-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.range-info label {
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
  font-weight: 600;
}

.combo-count {
  font-size: 18px;
  font-weight: 600;
  color: #2e7d32;
}

.turn-input,
.iterations-input {
  margin-bottom: 16px;
}

.turn-input label,
.iterations-input label {
  display: block;
  font-size: 14px;
  margin-bottom: 8px;
  color: #666;
}

.turn-card-input {
  font-family: monospace;
  font-size: 18px;
  padding: 12px;
  width: 80px;
  text-align: center;
  text-transform: capitalize;
}

.iterations-input select {
  padding: 8px 12px;
  font-size: 14px;
}

.bottom-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.create-btn {
  padding: 16px 32px;
  font-size: 16px;
}

.bottom-actions button {
  padding: 12px 24px;
}
</style>

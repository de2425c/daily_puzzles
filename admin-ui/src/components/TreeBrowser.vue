<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '../api'
import RangeGrid from './RangeGrid.vue'

const props = defineProps({
  simId: {
    type: String,
    required: true
  },
  board: {
    type: String,
    required: true
  },
  ipPosition: {
    type: String,
    required: true
  },
  oopPosition: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['spot-created'])

// Current path in the tree
const currentPath = ref('r:0')
const pathHistory = ref([])  // Array of {path, label, player}

// Tree node data
const nodeData = ref(null)
const rangeData = ref(null)
const handOrder = ref(null)
const loading = ref(false)
const error = ref(null)

// Load node data at current path
async function loadNode() {
  loading.value = true
  error.value = null

  try {
    // Load hand order if not cached
    if (!handOrder.value) {
      handOrder.value = await api.getHandOrder()
    }

    // Load actions at current path
    nodeData.value = await api.getTreeActions(props.simId, currentPath.value)

    // Load ranges at current path
    rangeData.value = await api.getTreeRanges(props.simId, currentPath.value)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

// Navigate to a child action
function selectAction(action) {
  // Add current state to history
  pathHistory.value.push({
    path: currentPath.value,
    label: getPathLabel(),
    player: currentPlayer.value
  })

  // Update path
  currentPath.value = action.path
  loadNode()
}

// Go back to a previous point in history
function goToHistory(index) {
  if (index < 0) {
    // Go to root
    currentPath.value = 'r:0'
    pathHistory.value = []
  } else {
    currentPath.value = pathHistory.value[index].path
    pathHistory.value = pathHistory.value.slice(0, index)
  }
  loadNode()
}

// Get current player name
const currentPlayer = computed(() => {
  if (!nodeData.value) return ''
  if (nodeData.value.is_terminal) return 'Terminal'
  return nodeData.value.position === 'IP' ? props.ipPosition : props.oopPosition
})

// Get the range to display (current player's range)
const displayRange = computed(() => {
  if (!rangeData.value) return null
  if (!nodeData.value || nodeData.value.is_terminal) return null

  return nodeData.value.position === 'IP'
    ? rangeData.value.ip_range
    : rangeData.value.oop_range
})

// Build action line description
function getPathLabel() {
  if (currentPath.value === 'r:0') return 'Start'

  const parts = currentPath.value.split(':').slice(2)  // Skip 'r' and '0'
  const labels = []
  let player = 1  // OOP acts first

  for (const part of parts) {
    const playerName = player === 1 ? props.oopPosition : props.ipPosition
    let actionLabel = ''

    if (part === 'c') {
      actionLabel = 'checks'
    } else if (part === 'f') {
      actionLabel = 'folds'
    } else if (part.startsWith('b')) {
      const amount = parseInt(part.slice(1)) / 1000000
      actionLabel = `bets ${amount.toFixed(1)}bb`
    } else if (part === 'a') {
      actionLabel = 'all-in'
    }

    labels.push(`${playerName} ${actionLabel}`)
    player = 1 - player
  }

  return labels.join(' → ')
}

// Handle combo selection from range grid
async function handleComboSelect(combo) {
  try {
    const result = await api.createSpotAtPath(props.simId, currentPath.value, combo)
    emit('spot-created', result.spot_id)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

// Format action for display
function formatActionLabel(action) {
  return action.label
}

// Load on mount and when simId changes
onMounted(loadNode)
watch(() => props.simId, loadNode)
</script>

<template>
  <div class="tree-browser">
    <!-- Breadcrumb / Path History -->
    <div class="path-breadcrumb">
      <span class="crumb root" @click="goToHistory(-1)">Root</span>
      <template v-for="(item, idx) in pathHistory" :key="idx">
        <span class="crumb-separator">→</span>
        <span class="crumb" @click="goToHistory(idx)">{{ item.label }}</span>
      </template>
      <template v-if="pathHistory.length > 0 || currentPath !== 'r:0'">
        <span class="crumb-separator">→</span>
        <span class="crumb current">{{ getPathLabel() }}</span>
      </template>
    </div>

    <!-- Loading / Error States -->
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <!-- Node Content -->
    <div v-else-if="nodeData" class="node-content">
      <!-- Terminal Node -->
      <div v-if="nodeData.is_terminal" class="terminal-node">
        <div class="terminal-label">Showdown / Terminal</div>
        <div class="range-info">
          <span>IP: {{ rangeData?.ip_combos || 0 }} combos</span>
          <span>OOP: {{ rangeData?.oop_combos || 0 }} combos</span>
          <span>Pot: {{ rangeData?.pot_size_bb?.toFixed(1) || 0 }}bb</span>
        </div>
      </div>

      <!-- Decision Node -->
      <div v-else class="decision-node">
        <div class="player-to-act">
          <strong>{{ currentPlayer }}</strong> to act
          <span class="pot-size">(Pot: {{ rangeData?.pot_size_bb?.toFixed(1) || 0 }}bb)</span>
        </div>

        <!-- Available Actions -->
        <div class="actions-list">
          <div class="actions-label">Available actions:</div>
          <div class="action-buttons">
            <button
              v-for="action in nodeData.actions"
              :key="action.path"
              class="action-btn"
              @click="selectAction(action)"
            >
              {{ formatActionLabel(action) }}
            </button>
          </div>
        </div>

        <!-- Range Grid -->
        <div v-if="displayRange && handOrder" class="range-display">
          <div class="range-header">
            {{ currentPlayer }}'s Range
            <span class="combo-count">({{ nodeData.position === 'IP' ? rangeData?.ip_combos : rangeData?.oop_combos }} combos)</span>
            <span class="click-hint">Click a hand to create a spot</span>
          </div>
          <RangeGrid
            :range="displayRange"
            :hand-order="handOrder"
            :board="board"
            :clickable="true"
            :strategy="rangeData?.strategy"
            :action-names="rangeData?.action_names"
            @select-combo="handleComboSelect"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tree-browser {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.path-breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 10px 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.crumb {
  color: #1976d2;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
}

.crumb:hover {
  background: #e3f2fd;
}

.crumb.current {
  color: #333;
  font-weight: 600;
  cursor: default;
}

.crumb.current:hover {
  background: transparent;
}

.crumb-separator {
  color: #999;
}

.loading {
  padding: 20px;
  text-align: center;
  color: #666;
}

.error {
  padding: 12px;
  background: #ffebee;
  color: #c62828;
  border-radius: 6px;
}

.node-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.terminal-node {
  padding: 20px;
  background: #f5f5f5;
  border-radius: 8px;
  text-align: center;
}

.terminal-label {
  font-size: 18px;
  font-weight: 600;
  color: #666;
  margin-bottom: 12px;
}

.range-info {
  display: flex;
  justify-content: center;
  gap: 20px;
  color: #666;
  font-size: 13px;
}

.decision-node {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.player-to-act {
  font-size: 16px;
}

.player-to-act strong {
  color: #1976d2;
}

.pot-size {
  color: #666;
  font-size: 13px;
  margin-left: 8px;
}

.actions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.actions-label {
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
  font-weight: 600;
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.action-btn {
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.action-btn:hover {
  background: #e3f2fd;
  border-color: #1976d2;
}

.range-display {
  margin-top: 8px;
}

.range-header {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}

.combo-count {
  font-weight: normal;
  color: #666;
  font-size: 12px;
  margin-left: 6px;
}

.click-hint {
  font-size: 10px;
  font-weight: normal;
  color: #999;
  margin-left: 12px;
}
</style>

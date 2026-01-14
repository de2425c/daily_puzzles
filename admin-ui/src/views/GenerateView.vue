<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import PreflopBuilder from '../components/PreflopBuilder.vue'

const router = useRouter()

// Tab state
const activeTab = ref('custom')  // 'preset' or 'custom'

// Preset form state
const board = ref('')
const scenario = ref('srp_utg_vs_bb')
const iterations = ref(500)
const loading = ref(false)
const error = ref(null)

// Detect street from board length
const detectedStreet = computed(() => {
  const len = board.value.replace(/\s/g, '').length
  if (len === 0) return 'flop (random)'
  if (len === 6) return 'flop'
  if (len === 8) return 'turn'
  if (len === 10) return 'river'
  return 'invalid'
})

const isValidBoard = computed(() => {
  const len = board.value.replace(/\s/g, '').length
  return len === 0 || len === 6 || len === 8 || len === 10
})

async function generate() {
  if (!isValidBoard.value) {
    error.value = 'Board must be 3 cards (flop), 4 cards (turn), or 5 cards (river)'
    return
  }

  loading.value = true
  error.value = null

  try {
    const result = await api.generate(board.value, scenario.value, iterations.value)
    // Redirect to the new sim
    if (result.sim_id) {
      router.push(`/sims/${result.sim_id}`)
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
    loading.value = false
  }
}

// Custom scenario handlers
function onScenarioReady(summary) {
  // Scenario is ready, user can now generate
  console.log('Scenario ready:', summary)
}

function onSimCreated(result) {
  // Redirect to the new sim
  if (result.sim_id) {
    router.push(`/sims/${result.sim_id}`)
  }
}
</script>

<template>
  <div class="generate-view">
    <h2>Generate New Spots</h2>
    <p class="subtitle">Run the solver and extract interesting spots</p>

    <!-- Tab Navigation -->
    <div class="tabs">
      <button
        :class="{ active: activeTab === 'custom' }"
        @click="activeTab = 'custom'"
      >
        Custom Scenario
      </button>
      <button
        :class="{ active: activeTab === 'preset' }"
        @click="activeTab = 'preset'"
      >
        Preset Scenarios
      </button>
    </div>

    <!-- Custom Scenario Tab -->
    <div v-if="activeTab === 'custom'" class="tab-content">
      <p class="tab-description">
        Build a custom preflop scenario by selecting actions. Uses real GTO ranges.
      </p>
      <PreflopBuilder
        @scenario-ready="onScenarioReady"
        @sim-created="onSimCreated"
      />
    </div>

    <!-- Preset Scenarios Tab -->
    <div v-if="activeTab === 'preset'" class="tab-content">
      <div class="card form-card">
        <div class="form-group">
          <label>Board (leave empty for random flop)</label>
          <input
            v-model="board"
            placeholder="Ah7d2c (flop) | Ah7d2c8h (turn) | Ah7d2c8hKs (river)"
            :disabled="loading"
            :class="{ invalid: !isValidBoard }"
          />
          <div class="street-indicator" :class="{ invalid: !isValidBoard }">
            Street: {{ detectedStreet }}
          </div>
        </div>

        <div class="form-group">
          <label>Scenario</label>
          <select v-model="scenario" :disabled="loading">
            <option value="srp_utg_vs_bb">SRP: UTG vs BB</option>
            <option value="srp_btn_vs_bb">SRP: BTN vs BB</option>
            <option value="srp_co_vs_bb">SRP: CO vs BB</option>
          </select>
        </div>

        <div class="form-group">
          <label>Iterations</label>
          <select v-model="iterations" :disabled="loading">
            <option :value="250">250 (fast)</option>
            <option :value="500">500 (default)</option>
            <option :value="1000">1000 (accurate)</option>
          </select>
        </div>

        <button
          class="primary generate-btn"
          @click="generate"
          :disabled="loading"
        >
          {{ loading ? 'Running solver...' : 'Generate Spots' }}
        </button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <div v-if="loading" class="loading-overlay">
      <div class="spinner"></div>
      <p>Running solver... This may take 1-2 minutes.</p>
    </div>
  </div>
</template>

<style scoped>
.subtitle {
  color: #666;
  margin-top: -10px;
  margin-bottom: 20px;
}

.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid #ddd;
  padding-bottom: 0;
}

.tabs button {
  padding: 12px 24px;
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: #666;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.2s;
}

.tabs button:hover {
  color: #333;
}

.tabs button.active {
  color: #1976d2;
  border-bottom-color: #1976d2;
}

.tab-content {
  margin-top: 20px;
}

.tab-description {
  color: #666;
  font-size: 14px;
  margin-bottom: 20px;
}

.form-card {
  max-width: 500px;
}

.form-group {
  margin-bottom: 16px;
}

.street-indicator {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
  text-transform: capitalize;
}

.street-indicator.invalid {
  color: #dc3545;
}

input.invalid {
  border-color: #dc3545;
}

.generate-btn {
  width: 100%;
  padding: 12px;
  font-size: 16px;
}

.result {
  max-width: 500px;
  margin-top: 20px;
  text-align: center;
}

.result h3 {
  color: #28a745;
  margin-top: 0;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error {
  background: #ffebee;
  color: #c62828;
  padding: 12px;
  border-radius: 4px;
  margin-top: 16px;
  max-width: 500px;
}
</style>

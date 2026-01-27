<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute()
const router = useRouter()

const sim = ref(null)
const loading = ref(true)
const generating = ref(false)
const error = ref(null)

onMounted(async () => {
  try {
    sim.value = await api.getSim(route.params.id)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatScenario(scenario) {
  return scenario.replace(/_/g, ' ').toUpperCase()
}

async function generateRandomSpot() {
  generating.value = true
  error.value = null

  try {
    const result = await api.generateRandomSpot(sim.value.id)
    // Navigate to spot review
    router.push(`/spots/${result.spot_id}`)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    generating.value = false
  }
}

function goBack() {
  router.push('/sims')
}
</script>

<template>
  <div class="sim-view">
    <div v-if="loading" class="loading">Loading sim...</div>
    <div v-else-if="error && !sim" class="error">{{ error }}</div>
    <template v-else-if="sim">
      <!-- Header -->
      <div class="header card">
        <div class="board-display">
          <span v-for="(card, i) in sim.board.match(/.{2}/g)" :key="i" class="card-chip">
            {{ card }}
          </span>
        </div>
        <div class="street-badge">{{ sim.street }}</div>
        <div class="scenario">{{ formatScenario(sim.scenario) }}</div>
        <div class="positions">{{ sim.ip_position }} vs {{ sim.oop_position }}</div>
      </div>

      <!-- Details -->
      <div class="card">
        <h3>Sim Details</h3>
        <div class="details-grid">
          <div class="detail">
            <label>Board</label>
            <span class="monospace">{{ sim.board }}</span>
          </div>
          <div class="detail">
            <label>Street</label>
            <span class="street-value">{{ sim.street }}</span>
          </div>
          <div class="detail">
            <label>Scenario</label>
            <span>{{ formatScenario(sim.scenario) }}</span>
          </div>
          <div class="detail">
            <label>Positions</label>
            <span>{{ sim.ip_position }} (IP) vs {{ sim.oop_position }} (OOP)</span>
          </div>
          <div class="detail">
            <label>Stack Size</label>
            <span>{{ sim.stack_size_bb }}bb</span>
          </div>
          <div class="detail">
            <label>Iterations</label>
            <span>{{ sim.iterations }}</span>
          </div>
          <div class="detail">
            <label>Created</label>
            <span>{{ formatDate(sim.created_at) }}</span>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="error" class="error card">{{ error }}</div>

      <!-- Actions -->
      <div class="action-buttons">
        <button
          class="primary browse-btn"
          @click="router.push(`/sims/${sim.id}/browse`)"
        >
          Browse Tree
        </button>
        <button
          class="secondary generate-btn"
          @click="generateRandomSpot"
          :disabled="generating"
        >
          {{ generating ? 'Generating...' : 'Random Spot' }}
        </button>
        <button
          v-if="sim.street === 'flop'"
          class="secondary"
          @click="router.push(`/sims/${sim.id}/build-turn`)"
        >
          Create Turn Sim
        </button>
        <button
          v-if="sim.street === 'turn'"
          class="secondary"
          @click="router.push(`/sims/${sim.id}/build-river`)"
        >
          Create River Sim
        </button>
        <button @click="goBack">Back to Library</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.header {
  text-align: center;
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

.street-badge {
  display: inline-block;
  background: #e3f2fd;
  color: #1976d2;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  text-transform: capitalize;
  margin-bottom: 12px;
}

.scenario {
  font-size: 18px;
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

.details-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail label {
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
  font-weight: 600;
}

.monospace {
  font-family: monospace;
}

.street-value {
  text-transform: capitalize;
  color: #1976d2;
  font-weight: 500;
}

.action-buttons {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.browse-btn {
  padding: 16px 32px;
  font-size: 16px;
}

.generate-btn {
  padding: 12px 24px;
}

.action-buttons button {
  padding: 12px 24px;
}

.secondary {
  background: #f8f9fa;
  border: 2px solid #6c757d;
  color: #495057;
}

.secondary:hover {
  background: #e9ecef;
  border-color: #495057;
}
</style>

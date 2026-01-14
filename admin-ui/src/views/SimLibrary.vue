<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const sims = ref([])
const loading = ref(true)
const error = ref(null)

// Filter state
const streetFilter = ref('all')
const potTypeFilter = ref('all')

onMounted(async () => {
  try {
    sims.value = await api.getSims()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

// Determine pot type from scenario string
function getPotType(scenario) {
  if (!scenario) return 'srp'
  const lower = scenario.toLowerCase()
  if (lower.includes('4bet')) return '4bet'
  if (lower.includes('3bet')) return '3bet'
  return 'srp'
}

// Filtered sims based on current filters
const filteredSims = computed(() => {
  return sims.value.filter(sim => {
    // Street filter
    if (streetFilter.value !== 'all' && sim.street !== streetFilter.value) {
      return false
    }
    // Pot type filter
    if (potTypeFilter.value !== 'all' && getPotType(sim.scenario) !== potTypeFilter.value) {
      return false
    }
    return true
  })
})

function viewSim(id) {
  router.push(`/sims/${id}`)
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatScenario(scenario) {
  return scenario.replace(/_/g, ' ').toUpperCase()
}
</script>

<template>
  <div class="sim-library">
    <h2>Sim Library</h2>
    <p class="subtitle">{{ filteredSims.length }} of {{ sims.length }} sims</p>

    <!-- Filters -->
    <div class="filters">
      <div class="filter-group">
        <label>Street</label>
        <div class="filter-buttons">
          <button
            :class="{ active: streetFilter === 'all' }"
            @click="streetFilter = 'all'"
          >All</button>
          <button
            :class="{ active: streetFilter === 'flop' }"
            @click="streetFilter = 'flop'"
          >Flop</button>
          <button
            :class="{ active: streetFilter === 'turn' }"
            @click="streetFilter = 'turn'"
          >Turn</button>
          <button
            :class="{ active: streetFilter === 'river' }"
            @click="streetFilter = 'river'"
          >River</button>
        </div>
      </div>

      <div class="filter-group">
        <label>Pot Type</label>
        <div class="filter-buttons">
          <button
            :class="{ active: potTypeFilter === 'all' }"
            @click="potTypeFilter = 'all'"
          >All</button>
          <button
            :class="{ active: potTypeFilter === 'srp' }"
            @click="potTypeFilter = 'srp'"
          >SRP</button>
          <button
            :class="{ active: potTypeFilter === '3bet' }"
            @click="potTypeFilter = '3bet'"
          >3-Bet</button>
          <button
            :class="{ active: potTypeFilter === '4bet' }"
            @click="potTypeFilter = '4bet'"
          >4-Bet</button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading">Loading sims...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="sims.length === 0" class="empty">
      No sims stored yet. <router-link to="/generate">Generate some!</router-link>
    </div>
    <div v-else-if="filteredSims.length === 0" class="empty">
      No sims match the current filters.
    </div>
    <div v-else class="sim-grid">
      <div
        v-for="sim in filteredSims"
        :key="sim.id"
        class="sim-card card"
        @click="viewSim(sim.id)"
      >
        <div class="sim-header">
          <span class="board">{{ sim.board }}</span>
          <span class="date">{{ formatDate(sim.created_at) }}</span>
        </div>
        <div class="sim-meta">
          <span class="tag street-tag">{{ sim.street }}</span>
          <span class="tag">{{ formatScenario(sim.scenario) }}</span>
          <span class="tag">{{ sim.stack_size_bb }}bb</span>
        </div>
        <div class="sim-positions">
          {{ sim.ip_position }} vs {{ sim.oop_position }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.subtitle {
  color: #666;
  margin-top: -10px;
  margin-bottom: 20px;
}

.filters {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-group label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.filter-buttons {
  display: flex;
  gap: 4px;
}

.filter-buttons button {
  padding: 6px 12px;
  font-size: 13px;
  border: 1px solid #ddd;
  background: #fff;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-buttons button:hover {
  border-color: #2196f3;
  color: #2196f3;
}

.filter-buttons button.active {
  background: #2196f3;
  border-color: #2196f3;
  color: #fff;
}

.empty {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.sim-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.sim-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.sim-card:hover {
  transform: translateY(-2px);
}

.sim-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.board {
  font-family: monospace;
  font-size: 18px;
  font-weight: bold;
}

.date {
  font-size: 12px;
  color: #999;
}

.sim-meta {
  margin-bottom: 12px;
}

.sim-positions {
  padding-top: 12px;
  border-top: 1px solid #eee;
  color: #666;
  font-size: 14px;
}

.street-tag {
  text-transform: capitalize;
  background: #e3f2fd;
  color: #1976d2;
}
</style>

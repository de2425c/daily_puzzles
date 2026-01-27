<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import TreeBrowser from '../components/TreeBrowser.vue'

const route = useRoute()
const router = useRouter()

const sim = ref(null)
const loading = ref(true)
const error = ref(null)

// Day plan context from query params
const dayPlanContext = computed(() => {
  if (route.query.dayPlanId && route.query.slotId) {
    return {
      dayPlanId: route.query.dayPlanId,
      slotId: route.query.slotId,
      scheduledDate: route.query.scheduledDate,
      returnTo: route.query.returnTo
    }
  }
  return null
})

async function loadSim() {
  loading.value = true
  error.value = null

  try {
    sim.value = await api.getSim(route.params.id)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function handleSpotCreated(spotId) {
  // Navigate to the spot review page with day plan context if available
  if (dayPlanContext.value) {
    router.push({
      path: `/spots/${spotId}`,
      query: {
        dayPlanId: dayPlanContext.value.dayPlanId,
        slotId: dayPlanContext.value.slotId,
        scheduledDate: dayPlanContext.value.scheduledDate,
        returnTo: dayPlanContext.value.returnTo
      }
    })
  } else {
    router.push(`/spots/${spotId}`)
  }
}

onMounted(loadSim)
</script>

<template>
  <div class="sim-browser">
    <div class="header">
      <router-link v-if="dayPlanContext" :to="dayPlanContext.returnTo" class="back-link">&larr; Back to Day Plan</router-link>
      <router-link v-else to="/sims" class="back-link">&larr; Back to Sims</router-link>
      <h1>Browse Sim</h1>
      <div v-if="dayPlanContext" class="day-plan-badge">
        Creating puzzle for {{ dayPlanContext.scheduledDate }}
      </div>
    </div>

    <div v-if="loading" class="loading">Loading sim...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <div v-else-if="sim" class="browser-content">
      <!-- Sim Info -->
      <div class="sim-info">
        <div class="info-row">
          <span class="label">Board:</span>
          <span class="board">{{ sim.board }}</span>
        </div>
        <div class="info-row">
          <span class="label">Positions:</span>
          <span>{{ sim.ip_position }} (IP) vs {{ sim.oop_position }} (OOP)</span>
        </div>
        <div class="info-row">
          <span class="label">Stack:</span>
          <span>{{ sim.stack_size_bb }}bb</span>
        </div>
        <div class="info-row">
          <span class="label">Street:</span>
          <span class="street">{{ sim.street }}</span>
        </div>
      </div>

      <!-- Tree Browser -->
      <div class="tree-section">
        <TreeBrowser
          :sim-id="sim.id"
          :board="sim.board"
          :ip-position="sim.ip_position"
          :oop-position="sim.oop_position"
          @spot-created="handleSpotCreated"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.sim-browser {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  margin-bottom: 20px;
}

.back-link {
  color: #1976d2;
  text-decoration: none;
  font-size: 13px;
}

.back-link:hover {
  text-decoration: underline;
}

h1 {
  margin: 8px 0 0;
  font-size: 24px;
}

.day-plan-badge {
  margin-top: 8px;
  padding: 6px 12px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  display: inline-block;
}

.loading {
  padding: 40px;
  text-align: center;
  color: #666;
}

.error {
  padding: 16px;
  background: #ffebee;
  color: #c62828;
  border-radius: 8px;
}

.browser-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.sim-info {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.label {
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
}

.board {
  font-family: monospace;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}

.street {
  text-transform: capitalize;
  font-weight: 500;
}

.tree-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
</style>

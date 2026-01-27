<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import PreflopConfigSelector from '../components/PreflopConfigSelector.vue'
import PreflopConfigTree from '../components/PreflopConfigTree.vue'
import BoardSelector from '../components/BoardSelector.vue'
import ActionPathSelector from '../components/ActionPathSelector.vue'
import SlotEditorPanel from '../components/SlotEditorPanel.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref(null)
const dayPlan = ref(null)

// UI State
const selectingConfig = ref(null) // 0 or 1 when selecting preflop for that config
const selectedSlot = ref(null) // The slot being worked on
const showBoardSelector = ref(false)
const showActionPathSelector = ref(false)
const showSlotEditor = ref(false)

// Loading states
const creatingConfig = ref(false)
const creatingSim = ref(false)

// Existing sims for each config
const existingSims = ref({ 0: [], 1: [] })

const scheduledDate = computed(() => route.params.date)

function formatDate(dateStr) {
  const date = new Date(dateStr + 'T00:00:00')
  const options = { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }
  return date.toLocaleDateString('en-US', options)
}

async function loadDayPlan() {
  loading.value = true
  error.value = null

  try {
    dayPlan.value = await api.getDayPlan(scheduledDate.value)
    // Load existing sims for each config
    await loadExistingSims()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadExistingSims() {
  if (!dayPlan.value) return

  for (let i = 0; i < dayPlan.value.configs.length; i++) {
    try {
      existingSims.value[i] = await api.getExistingSimsForConfig(dayPlan.value.id, i)
    } catch (e) {
      console.error(`Failed to load existing sims for config ${i}:`, e)
      existingSims.value[i] = []
    }
  }
}

onMounted(() => loadDayPlan())

watch(() => route.params.date, () => {
  loadDayPlan()
})

// Config selection
function startSelectConfig(configIdx) {
  selectingConfig.value = configIdx
}

function cancelSelectConfig() {
  selectingConfig.value = null
}

function resetConfig(configIdx) {
  // Start selecting a new preflop for this config index
  startSelectConfig(configIdx)
}

async function onPreflopSelected(preflopPath) {
  if (selectingConfig.value === null) return

  creatingConfig.value = true
  error.value = null

  try {
    const configIdx = selectingConfig.value
    dayPlan.value = await api.setPreflopConfig(
      dayPlan.value.id,
      configIdx,
      preflopPath
    )
    selectingConfig.value = null
    // Reload existing sims for this config
    try {
      existingSims.value[configIdx] = await api.getExistingSimsForConfig(dayPlan.value.id, configIdx)
    } catch (e) {
      existingSims.value[configIdx] = []
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    creatingConfig.value = false
  }
}

// Slot actions
function onSlotClick(slot, config) {
  selectedSlot.value = { slot, config }

  if (slot.status === 'empty') {
    if (slot.street === 'flop') {
      showBoardSelector.value = true
    } else {
      // Turn/river - need to select action path from parent
      showActionPathSelector.value = true
    }
  } else if (slot.status === 'sim_ready') {
    // Ready to create puzzle - go to spot review
    showSlotEditor.value = true
  }
}

function closeModals() {
  showBoardSelector.value = false
  showActionPathSelector.value = false
  showSlotEditor.value = false
  selectedSlot.value = null
}

async function onLinkSim(slot, simId) {
  error.value = null

  try {
    dayPlan.value = await api.linkSlotSim(dayPlan.value.id, slot.id, simId)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

async function onBoardSelected(board) {
  if (!selectedSlot.value) return

  creatingSim.value = true
  error.value = null

  try {
    dayPlan.value = await api.createSlotSim(
      dayPlan.value.id,
      selectedSlot.value.slot.id,
      board
    )
    closeModals()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    creatingSim.value = false
  }
}

async function onActionPathSelected(actionPath, card) {
  if (!selectedSlot.value) return

  creatingSim.value = true
  error.value = null

  try {
    dayPlan.value = await api.createChildSlotSim(
      dayPlan.value.id,
      selectedSlot.value.slot.id,
      actionPath,
      card
    )
    closeModals()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    creatingSim.value = false
  }
}

function goToSpotReview(slot) {
  // Navigate to sim browser with day plan context
  router.push({
    path: `/sims/${slot.sim_id}/browse`,
    query: {
      dayPlanId: dayPlan.value.id,
      slotId: slot.id,
      scheduledDate: dayPlan.value.scheduled_date,
      returnTo: route.fullPath
    }
  })
}

async function onSlotComplete(puzzleId) {
  if (!selectedSlot.value) return

  try {
    dayPlan.value = await api.updateSlot(
      dayPlan.value.id,
      selectedSlot.value.slot.id,
      { puzzle_id: puzzleId, status: 'complete' }
    )
    closeModals()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

// Get parent slot for a turn/river slot
function getParentSlot(slot, config) {
  if (!slot.parent_slot_id) return null
  return config.slots.find(s => s.id === slot.parent_slot_id)
}

// Check if slot is blocked (parent not ready)
function isSlotBlocked(slot, config) {
  if (slot.street === 'flop') return false
  const parent = getParentSlot(slot, config)
  return !parent || (parent.status !== 'sim_ready' && parent.status !== 'complete')
}

// Count completed slots
const completedSlots = computed(() => {
  if (!dayPlan.value?.configs) return 0
  return dayPlan.value.configs.reduce((acc, config) => {
    return acc + config.slots.filter(s => s.status === 'complete').length
  }, 0)
})

const totalSlots = computed(() => {
  if (!dayPlan.value?.configs) return 0
  return dayPlan.value.configs.reduce((acc, config) => acc + config.slots.length, 0)
})

function goHome() {
  router.push('/')
}
</script>

<template>
  <div class="day-plan-creator">
    <header class="page-header">
      <button class="back-btn" @click="goHome">&larr; Back</button>
      <div class="header-content">
        <h1>Day Plan: {{ formatDate(scheduledDate) }}</h1>
        <div v-if="dayPlan" class="progress-badge">
          {{ completedSlots }} / {{ totalSlots }} puzzles complete
        </div>
      </div>
    </header>

    <div v-if="loading" class="loading">Loading day plan...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="dayPlan">
      <!-- Config Selection Mode -->
      <div v-if="selectingConfig !== null" class="config-selector-panel">
        <div class="panel-header">
          <h2>Select Preflop Scenario for Config {{ selectingConfig + 1 }}</h2>
          <button class="cancel-btn" @click="cancelSelectConfig">Cancel</button>
        </div>
        <PreflopConfigSelector
          :disabled="creatingConfig"
          @select="onPreflopSelected"
        />
        <div v-if="creatingConfig" class="loading">Creating config...</div>
      </div>

      <!-- Main View -->
      <template v-else>
        <div class="configs-grid">
          <!-- Config 1 -->
          <div class="config-panel">
            <div class="config-header">
              <h2>Config 1</h2>
              <template v-if="dayPlan.configs[0]">
                <span class="config-desc">{{ dayPlan.configs[0].description }}</span>
                <button
                  class="reset-config-btn"
                  @click="resetConfig(0)"
                  title="Change preflop scenario"
                >
                  Reset
                </button>
              </template>
              <button
                v-else
                class="select-preflop-btn"
                @click="startSelectConfig(0)"
              >
                Select Preflop
              </button>
            </div>
            <PreflopConfigTree
              v-if="dayPlan.configs[0]"
              :config="dayPlan.configs[0]"
              :existing-sims="existingSims[0] || []"
              @slot-click="(slot) => onSlotClick(slot, dayPlan.configs[0])"
              @link-sim="(slot, simId) => onLinkSim(slot, simId)"
            />
          </div>

          <!-- Config 2 -->
          <div class="config-panel">
            <div class="config-header">
              <h2>Config 2</h2>
              <template v-if="dayPlan.configs[1]">
                <span class="config-desc">{{ dayPlan.configs[1].description }}</span>
                <button
                  class="reset-config-btn"
                  @click="resetConfig(1)"
                  title="Change preflop scenario"
                >
                  Reset
                </button>
              </template>
              <button
                v-else
                class="select-preflop-btn"
                @click="startSelectConfig(1)"
                :disabled="!dayPlan.configs[0]"
              >
                Select Preflop
              </button>
            </div>
            <PreflopConfigTree
              v-if="dayPlan.configs[1]"
              :config="dayPlan.configs[1]"
              :existing-sims="existingSims[1] || []"
              @slot-click="(slot) => onSlotClick(slot, dayPlan.configs[1])"
              @link-sim="(slot, simId) => onLinkSim(slot, simId)"
            />
          </div>
        </div>

        <!-- Board Selector Modal -->
        <BoardSelector
          v-if="showBoardSelector && selectedSlot"
          :visible="showBoardSelector"
          :loading="creatingSim"
          @select="onBoardSelected"
          @close="closeModals"
        />

        <!-- Action Path Selector Modal -->
        <ActionPathSelector
          v-if="showActionPathSelector && selectedSlot"
          :visible="showActionPathSelector"
          :slot="selectedSlot.slot"
          :config="selectedSlot.config"
          :loading="creatingSim"
          @select="onActionPathSelected"
          @close="closeModals"
        />

        <!-- Slot Editor Panel -->
        <SlotEditorPanel
          v-if="showSlotEditor && selectedSlot"
          :visible="showSlotEditor"
          :slot="selectedSlot.slot"
          :day-plan-id="dayPlan.id"
          @complete="onSlotComplete"
          @close="closeModals"
          @go-to-review="goToSpotReview(selectedSlot.slot)"
        />
      </template>
    </template>
  </div>
</template>

<style scoped>
.day-plan-creator {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.back-btn {
  padding: 8px 12px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.back-btn:hover {
  background: #e9ecef;
}

.header-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-content h1 {
  margin: 0;
  font-size: 24px;
}

.progress-badge {
  padding: 6px 12px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}

.loading {
  color: #666;
  font-style: italic;
  padding: 40px;
  text-align: center;
}

.error {
  background: #ffebee;
  color: #c62828;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

/* Config Selector Panel */
.config-selector-panel {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.config-selector-panel .panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.config-selector-panel h2 {
  margin: 0;
  font-size: 18px;
}

.cancel-btn {
  padding: 6px 12px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.cancel-btn:hover {
  background: #e9ecef;
}

/* Configs Grid */
.configs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.config-panel {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.config-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #eee;
}

.config-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.config-desc {
  font-size: 13px;
  color: #666;
  flex: 1;
}

.reset-config-btn {
  padding: 4px 10px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
}

.reset-config-btn:hover {
  background: #e9ecef;
  color: #333;
}

.select-preflop-btn {
  padding: 8px 16px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.select-preflop-btn:hover:not(:disabled) {
  background: #1565c0;
}

.select-preflop-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 1024px) {
  .configs-grid {
    grid-template-columns: 1fr;
  }
}
</style>

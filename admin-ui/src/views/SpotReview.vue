<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import RangeGrid from '../components/RangeGrid.vue'
import CardPicker from '../components/CardPicker.vue'

const route = useRoute()
const router = useRouter()

const spot = ref(null)
const loading = ref(true)
const saving = ref(false)
const regenerating = ref(false)
const error = ref(null)

// Range data for RangeGrid
const heroRange = ref(null)
const handOrder = ref(null)

// Regenerate options
const showRegenOptions = ref(false)
const regenPosition = ref('')  // '', 'IP', 'OOP'
const regenCombo = ref('')     // '' or specific combo like 'AhKs'

// Card picker
const showCardPicker = ref(false)

// Form data
const questionText = ref('')
const difficulty = ref(2)
const tags = ref([])
const newTag = ref('')
const scheduledDate = ref('')

// Action data: {action: string, selected: bool, correct: bool, explanation: string}
const actionData = ref([])

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

// Get scheduled date from day plan context or use today
const today = new Date().toISOString().split('T')[0]
scheduledDate.value = route.query.scheduledDate || today

// Suggested tags based on spot
const suggestedTags = computed(() => {
  if (!spot.value) return []
  return [
    'cash', '6max', `${Math.round(spot.value.stack_size_bb)}bb`,
    'srp', spot.value.street
  ]
})

// Blocked cards for card picker (board cards)
const blockedCards = computed(() => {
  if (!spot.value?.board) return []
  // Parse board string like "AcQd9c" into ["Ac", "Qd", "9c"]
  return spot.value.board.match(/.{2}/g) || []
})

function openCardPicker() {
  showCardPicker.value = true
}

function onCardPickerSelect(combo) {
  showCardPicker.value = false
  handleComboSelect(combo)
}

async function loadSpot(spotId) {
  loading.value = true
  error.value = null
  spot.value = null
  heroRange.value = null

  try {
    spot.value = await api.getSpot(spotId)

    // Initialize action data from available actions
    // Pre-select actions with >1% frequency and mark highest frequency as correct
    actionData.value = spot.value.available_actions.map(action => {
      const freq = spot.value.action_frequencies[action] || 0
      const isCorrect = action === spot.value.correct_action
      return {
        action,
        selected: freq > 0.01,  // Select if >1% frequency
        correct: isCorrect,
        explanation: ''
      }
    })

    tags.value = [...suggestedTags.value]
    questionText.value = `You are ${spot.value.hero_position} with ${spot.value.hero_combo}. What's your play?`

    // Fetch range data for the decision point
    await loadRangeData()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadRangeData() {
  if (!spot.value?.source_task_id || !spot.value?.tree_path) return

  try {
    // Extract sim ID from source_task_id (format: "sim-{uuid}")
    const simId = spot.value.source_task_id.replace('sim-', '')

    // Fetch hand order (cached after first load)
    if (!handOrder.value) {
      handOrder.value = await api.getHandOrder()
    }

    // Fetch ranges at this tree path
    const rangeData = await api.getTreeRanges(simId, spot.value.tree_path)

    // Determine which range is hero's based on position
    // IP = player 0, OOP = player 1
    const isHeroIP = spot.value.hero_position === spot.value.ip_position ||
      (spot.value.hero_position !== 'BB' && spot.value.hero_position !== 'SB')

    // Actually, we need to check the spot data for ip_position
    // The spot has hero_position and villain_position
    // In postflop, the positions like "BB", "BTN" etc are used
    // IP is typically BTN, CO, HJ etc vs BB who is OOP

    // Simple heuristic: BB/SB are usually OOP postflop
    const heroIsOOP = spot.value.hero_position === 'BB' || spot.value.hero_position === 'SB'

    heroRange.value = heroIsOOP ? rangeData.oop_range : rangeData.ip_range
  } catch (e) {
    console.error('Failed to load range data:', e)
    // Don't fail the whole load, just skip range display
  }
}

async function handleComboSelect(combo) {
  // Create spot at the same tree path with the selected combo
  // This preserves the action sequence and filtered ranges
  regenerating.value = true
  error.value = null

  try {
    const simId = spot.value.source_task_id.replace('sim-', '')

    // Use createSpotAtPath to preserve the action sequence
    const result = await api.createSpotAtPath(simId, spot.value.tree_path, combo)

    // Navigate to the new spot
    router.push(`/spots/${result.spot_id}`)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    regenerating.value = false
  }
}

// Load on mount
onMounted(() => loadSpot(route.params.id))

// Reload when route params change (for regenerate)
watch(() => route.params.id, (newId) => {
  if (newId) {
    loadSpot(newId)
  }
})

function formatFrequency(freq) {
  return `${(freq * 100).toFixed(0)}%`
}

function formatEV(ev) {
  return ev >= 0 ? `+${ev.toFixed(2)}bb` : `${ev.toFixed(2)}bb`
}

function formatAction(action) {
  if (!spot.value) return action

  // Detect if hero is facing a bet by checking the street actions
  const streetActions = spot.value.street_actions || []
  const decisionStreet = streetActions.find(s => s.street === spot.value.street)
  const facingBet = decisionStreet?.actions?.toLowerCase().includes(' bets ') ||
                    decisionStreet?.actions?.toLowerCase().includes(' raises ')

  // Match "Bet Xbb" format (new format with actual amounts)
  if (action.toLowerCase().startsWith('bet ')) {
    const actionType = facingBet ? 'Raise' : 'Bet'
    return action.replace(/^Bet/i, actionType)
  }

  // Match overbet patterns (legacy format)
  if (action.toLowerCase().startsWith('overbet')) {
    if (facingBet) {
      return action.replace(/^Overbet/i, 'Raise')
    }
    return action
  }

  return action
}

function addTag() {
  if (newTag.value && !tags.value.includes(newTag.value)) {
    tags.value.push(newTag.value)
    newTag.value = ''
  }
}

function removeTag(tag) {
  tags.value = tags.value.filter(t => t !== tag)
}

// Computed values for the form
const selectedActions = computed(() =>
  actionData.value.filter(a => a.selected).map(a => a.action)
)

const correctActions = computed(() =>
  actionData.value.filter(a => a.selected && a.correct).map(a => a.action)
)

const explanationsMap = computed(() => {
  const map = {}
  actionData.value.filter(a => a.selected).forEach(a => {
    map[a.action] = a.explanation
  })
  return map
})

async function approve() {
  if (!scheduledDate.value) {
    error.value = 'Please select a scheduled date'
    return
  }
  if (selectedActions.value.length < 2) {
    error.value = 'Please select at least 2 answer options'
    return
  }
  if (correctActions.value.length === 0) {
    error.value = 'Please mark at least one answer as correct'
    return
  }

  // Check that correct answers have explanations
  const missingExplanations = actionData.value
    .filter(a => a.selected && a.correct && !a.explanation.trim())
    .map(a => a.action)
  if (missingExplanations.length > 0) {
    error.value = `Please add explanations for correct answers: ${missingExplanations.join(', ')}`
    return
  }

  saving.value = true
  error.value = null

  try {
    const result = await api.approveSpot(spot.value.id, {
      question_text: questionText.value,
      answer_options: selectedActions.value,
      correct_answers: correctActions.value,
      explanations: explanationsMap.value,
      difficulty: difficulty.value,
      tags: tags.value,
      scheduled_date: scheduledDate.value,
    })

    // If we have day plan context, update the slot status
    if (dayPlanContext.value) {
      try {
        await api.updateSlot(
          dayPlanContext.value.dayPlanId,
          dayPlanContext.value.slotId,
          { puzzle_id: result.id, status: 'complete' }
        )
      } catch (e) {
        console.error('Failed to update slot:', e)
      }
      // Navigate back to day plan
      router.push(dayPlanContext.value.returnTo || `/day-plan/${scheduledDate.value}`)
    } else {
      router.push('/')
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

async function reject() {
  saving.value = true
  try {
    await api.rejectSpot(spot.value.id)
    // Go back to the sim page
    const simId = spot.value?.source_task_id?.replace('sim-', '') || ''
    router.push(simId ? `/sims/${simId}` : '/sims')
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function skip() {
  // Go back to the sim page
  const simId = spot.value?.source_task_id?.replace('sim-', '') || ''
  router.push(simId ? `/sims/${simId}` : '/sims')
}

function toggleRegenOptions() {
  showRegenOptions.value = !showRegenOptions.value
  if (showRegenOptions.value) {
    // Pre-fill with current spot's values
    regenPosition.value = ''
    regenCombo.value = ''
  }
}

function useCurrentPosition() {
  regenPosition.value = spot.value?.hero_position === spot.value?.ip_position ? 'IP' : 'OOP'
}

function useCurrentCombo() {
  regenCombo.value = spot.value?.hero_combo || ''
}

async function regenerate(withOptions = false) {
  // Extract sim ID from source_task_id (format: "sim-{uuid}")
  const sourceTaskId = spot.value?.source_task_id || ''
  const simId = sourceTaskId.replace('sim-', '')

  if (!simId) {
    error.value = 'Cannot regenerate: no source sim found'
    return
  }

  regenerating.value = true
  error.value = null
  showRegenOptions.value = false

  try {
    const options = withOptions ? {
      heroPosition: regenPosition.value || null,
      heroCombo: regenCombo.value || null,
    } : {}
    const result = await api.generateRandomSpot(simId, options)
    // Navigate to the new spot
    router.push(`/spots/${result.spot_id}`)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    regenerating.value = false
  }
}
</script>

<template>
  <div class="spot-review">
    <div v-if="loading" class="loading">Loading spot...</div>
    <div v-else-if="error && !spot" class="error">{{ error }}</div>
    <template v-else-if="spot">
      <div class="main-layout">
        <!-- LEFT SIDE: Puzzle Details -->
        <div class="left-panel">
          <!-- Top Row: Board + Hero side by side -->
          <div class="top-row">
            <div class="board-section">
              <div class="section-label">Board</div>
              <div class="board-cards">
                <span v-for="(card, i) in spot.board.match(/.{2}/g)" :key="i" class="card-chip">
                  {{ card }}
                </span>
              </div>
            </div>
            <div class="hero-section">
              <div class="hero-label">HERO</div>
              <div class="hero-info">
                <span class="hero-position">{{ spot.hero_position }}</span>
                <div class="hero-hand clickable" @click="openCardPicker" title="Click to change hand">
                  <span class="card-chip hero">{{ spot.hero_combo.slice(0,2) }}</span>
                  <span class="card-chip hero">{{ spot.hero_combo.slice(2,4) }}</span>
                  <span class="edit-icon">&#9998;</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Game Info Row -->
          <div class="info-row">
            <div class="info-item">
              <span class="info-label">Pot</span>
              <span class="info-value">{{ spot.pot_size_bb.toFixed(1) }}bb</span>
            </div>
            <div class="info-item">
              <span class="info-label">Stacks</span>
              <span class="info-value">{{ spot.stack_size_bb.toFixed(0) }}bb</span>
            </div>
            <div class="info-item">
              <span class="info-label">Villain</span>
              <span class="info-value">{{ spot.villain_position }}</span>
            </div>
          </div>

          <!-- Hand History -->
          <div class="history-section">
            <div class="section-label">Action</div>
            <div class="street-rows">
              <div
                v-for="(streetAction, i) in spot.street_actions"
                :key="i"
                class="street-row"
                :class="{ 'decision-street': streetAction.street === spot.street }"
              >
                <span class="street-name">{{ streetAction.street }}</span>
                <span v-if="streetAction.cards" class="street-cards">{{ streetAction.cards }}</span>
                <span class="street-actions">{{ streetAction.actions }}</span>
              </div>
            </div>
          </div>

          <!-- Optimal Play Table with Selection -->
          <div class="optimal-section">
            <div class="section-label">Optimal Play (Select answers to include)</div>
            <table>
              <thead>
                <tr>
                  <th class="col-select">Include</th>
                  <th>Action</th>
                  <th>Freq</th>
                  <th>EV</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(actionItem, index) in actionData"
                  :key="actionItem.action"
                  :class="{ correct: actionItem.action === spot.correct_action, selected: actionItem.selected }"
                >
                  <td class="col-select">
                    <input type="checkbox" v-model="actionData[index].selected" />
                  </td>
                  <td>
                    {{ formatAction(actionItem.action) }}
                    <span v-if="actionItem.action === spot.correct_action" class="check">&#10003;</span>
                  </td>
                  <td>{{ formatFrequency(spot.action_frequencies[actionItem.action]) }}</td>
                  <td>{{ formatEV(spot.ev_by_action[actionItem.action] || 0) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Hero's Range at Decision Point -->
          <div v-if="heroRange && handOrder" class="range-section">
            <div class="section-label">Hero's Range ({{ spot.hero_position }}) <span class="click-hint">Click a hand to select it</span></div>
            <RangeGrid
              :range="heroRange"
              :hand-order="handOrder"
              :board="spot.board"
              :hero-combo="spot.hero_combo"
              :clickable="true"
              @select-combo="handleComboSelect"
            />
          </div>
        </div>

        <!-- RIGHT SIDE: Question Form -->
        <div class="right-panel">
          <div class="form-section">
            <h2>Create Puzzle</h2>

            <div v-if="dayPlanContext" class="day-plan-badge">
              Creating puzzle for day plan: {{ dayPlanContext.scheduledDate }}
            </div>

            <div v-if="error" class="error">{{ error }}</div>

            <div class="form-group">
              <label>Question</label>
              <textarea v-model="questionText" rows="2"></textarea>
            </div>

            <!-- Answer Options with Correct/Explanation -->
            <div class="form-group answers-section">
              <label>Answer Options ({{ selectedActions.length }} selected, {{ correctActions.length }} correct)</label>
              <div class="answer-cards">
                <div
                  v-for="(actionItem, index) in actionData.filter(a => a.selected)"
                  :key="actionItem.action"
                  class="answer-card"
                  :class="{ 'is-correct': actionItem.correct }"
                >
                  <div class="answer-header">
                    <label class="correct-checkbox">
                      <input
                        type="checkbox"
                        :checked="actionItem.correct"
                        @change="actionData.find(a => a.action === actionItem.action).correct = $event.target.checked"
                      />
                      <span class="answer-action">{{ formatAction(actionItem.action) }}</span>
                      <span v-if="actionItem.correct" class="correct-badge">Correct</span>
                    </label>
                    <span class="answer-freq">{{ formatFrequency(spot.action_frequencies[actionItem.action]) }}</span>
                  </div>
                  <textarea
                    v-model="actionData.find(a => a.action === actionItem.action).explanation"
                    rows="2"
                    :placeholder="actionItem.correct ? 'Explain why this is correct...' : 'Optional: explain why this is wrong...'"
                    class="answer-explanation"
                  ></textarea>
                </div>
              </div>
            </div>

            <div class="form-row form-row-2">
              <div class="form-group">
                <label>Scheduled Date</label>
                <input type="date" v-model="scheduledDate" />
              </div>

              <div class="form-group">
                <label>Difficulty</label>
                <select v-model="difficulty">
                  <option :value="1">Easy</option>
                  <option :value="2">Medium</option>
                  <option :value="3">Hard</option>
                </select>
              </div>
            </div>

            <div class="form-group">
              <label>Tags</label>
              <div class="tags-editor">
                <span
                  v-for="tag in tags"
                  :key="tag"
                  class="tag removable"
                  @click="removeTag(tag)"
                >
                  {{ tag }} &times;
                </span>
                <input
                  v-model="newTag"
                  placeholder="Add tag..."
                  class="tag-input"
                  @keyup.enter="addTag"
                />
              </div>
            </div>

            <div class="action-buttons">
              <button class="primary" @click="approve" :disabled="saving || regenerating">
                {{ saving ? 'Saving...' : 'Approve & Save' }}
              </button>
              <button class="danger" @click="reject" :disabled="saving || regenerating">Reject</button>
              <button @click="skip" :disabled="saving || regenerating">Skip</button>
              <button class="regenerate" @click="regenerate(false)" :disabled="saving || regenerating">
                {{ regenerating ? 'Loading...' : 'Regenerate' }}
              </button>
              <button class="options-toggle" @click="toggleRegenOptions" :disabled="saving || regenerating">
                &#9881;
              </button>
            </div>

            <!-- Regenerate Options Panel -->
            <div v-if="showRegenOptions" class="regen-options">
              <h4>Regenerate Options</h4>
              <div class="regen-option-row">
                <label>Position</label>
                <div class="option-buttons">
                  <button :class="{ active: regenPosition === '' }" @click="regenPosition = ''">Any</button>
                  <button :class="{ active: regenPosition === 'IP' }" @click="regenPosition = 'IP'">IP</button>
                  <button :class="{ active: regenPosition === 'OOP' }" @click="regenPosition = 'OOP'">OOP</button>
                  <button class="use-current" @click="useCurrentPosition">Use Current</button>
                </div>
              </div>
              <div class="regen-option-row">
                <label>Hand</label>
                <div class="option-input">
                  <input v-model="regenCombo" placeholder="e.g., AhKs (leave empty for random)" />
                  <button class="use-current" @click="useCurrentCombo">Use Current</button>
                </div>
              </div>
              <div class="regen-actions">
                <button class="regenerate" @click="regenerate(true)" :disabled="regenerating">
                  {{ regenerating ? 'Loading...' : 'Generate with Options' }}
                </button>
                <button @click="showRegenOptions = false">Cancel</button>
              </div>
            </div>
          </div>

          <details class="debug-section">
            <summary>Debug JSON</summary>
            <pre>{{ JSON.stringify(spot, null, 2) }}</pre>
          </details>
        </div>
      </div>

      <!-- Card Picker Modal -->
      <CardPicker
        :visible="showCardPicker"
        :current-combo="spot?.hero_combo"
        :blocked-cards="blockedCards"
        @select="onCardPickerSelect"
        @close="showCardPicker = false"
      />
    </template>
  </div>
</template>

<style scoped>
.spot-review {
  max-width: 1400px;
  margin: 0 auto;
}

.main-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  align-items: start;
}

.left-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.right-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Top Row: Board + Hero */
.top-row {
  display: flex;
  gap: 24px;
  align-items: stretch;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.board-section {
  flex: 1;
}

.hero-section {
  background: linear-gradient(135deg, #1976d2, #1565c0);
  color: white;
  padding: 12px 20px;
  border-radius: 8px;
  text-align: center;
  min-width: 180px;
}

.hero-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 2px;
  opacity: 0.8;
  margin-bottom: 4px;
}

.hero-info {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}

.hero-position {
  font-size: 24px;
  font-weight: 700;
}

.hero-hand {
  display: flex;
  gap: 4px;
  position: relative;
}

.hero-hand.clickable {
  cursor: pointer;
  padding: 4px;
  margin: -4px;
  border-radius: 6px;
  transition: background 0.15s;
}

.hero-hand.clickable:hover {
  background: rgba(25, 118, 210, 0.1);
}

.hero-hand .edit-icon {
  display: none;
  position: absolute;
  right: -20px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  color: #1976d2;
}

.hero-hand.clickable:hover .edit-icon {
  display: block;
}

.section-label {
  font-size: 10px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 8px;
}

.board-cards {
  display: flex;
  gap: 6px;
}

.card-chip {
  font-family: monospace;
  font-size: 16px;
  font-weight: bold;
  padding: 6px 10px;
  background: #f8f9fa;
  border-radius: 4px;
  border: 2px solid #dee2e6;
  color: #333;
}

.card-chip.hero {
  background: rgba(255,255,255,0.95);
  border-color: rgba(255,255,255,0.5);
  font-size: 16px;
  padding: 6px 10px;
}

/* Info Row */
.info-row {
  display: flex;
  gap: 16px;
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.info-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.info-label {
  color: #666;
  font-size: 13px;
}

.info-value {
  font-weight: 600;
  font-size: 13px;
}

/* History */
.history-section {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.street-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.street-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 10px;
  border-radius: 4px;
  background: #f8f9fa;
  font-size: 13px;
}

.street-row.decision-street {
  background: #fff3cd;
  border: 1px solid #ffc107;
}

.street-name {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 10px;
  color: #666;
  min-width: 50px;
}

.street-cards {
  font-family: monospace;
  font-weight: bold;
  color: #333;
  min-width: 80px;
}

.street-actions {
  color: #333;
  flex: 1;
}

/* Optimal Play */
.optimal-section {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.range-section {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.click-hint {
  font-size: 10px;
  font-weight: normal;
  color: #999;
  margin-left: 8px;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid #eee;
  font-size: 13px;
}

th {
  font-size: 10px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
}

tr.correct {
  background: #d4edda;
}

tr.selected {
  background: #e3f2fd;
}

tr.selected.correct {
  background: #c8e6c9;
}

.col-select {
  width: 50px;
  text-align: center;
}

.col-select input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.check {
  color: #28a745;
  margin-left: 6px;
  font-weight: bold;
}

/* Form */
.form-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
}

.day-plan-badge {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}

.form-group {
  margin-bottom: 12px;
}

.form-group label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 8px 10px;
  font-size: 13px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-row-2 {
  grid-template-columns: 1fr 1fr;
}

.form-row-3 {
  grid-template-columns: 1fr 1fr 1fr;
}

/* Answer cards */
.answers-section {
  margin-top: 8px;
}

.answer-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.answer-card {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 10px 12px;
}

.answer-card.is-correct {
  background: #d4edda;
  border-color: #28a745;
}

.answer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.correct-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.correct-checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

.answer-action {
  font-weight: 600;
  font-size: 14px;
}

.correct-badge {
  background: #28a745;
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  font-weight: 600;
}

.answer-freq {
  color: #666;
  font-size: 12px;
}

.answer-explanation {
  width: 100%;
  font-size: 12px;
  padding: 6px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  resize: vertical;
}

.answer-card.is-correct .answer-explanation {
  border-color: #28a745;
}

.tags-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.tag {
  background: #e9ecef;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

.tag:hover {
  background: #dee2e6;
}

.tag-input {
  width: auto !important;
  min-width: 80px;
  flex: 1;
}

.action-buttons {
  display: flex;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.action-buttons button {
  padding: 10px 16px;
  font-size: 13px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.action-buttons button.primary {
  background: #1976d2;
  color: white;
}

.action-buttons button.danger {
  background: #dc3545;
  color: white;
}

.action-buttons button.regenerate {
  background: #17a2b8;
  color: white;
  margin-left: auto;
}

.action-buttons button.options-toggle {
  background: #6c757d;
  color: white;
  padding: 10px 12px;
  margin-left: 4px;
}

.action-buttons button:not(.primary):not(.danger):not(.regenerate):not(.options-toggle) {
  background: #e9ecef;
}

/* Regenerate Options */
.regen-options {
  margin-top: 16px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #dee2e6;
}

.regen-options h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #333;
}

.regen-option-row {
  margin-bottom: 12px;
}

.regen-option-row label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  margin-bottom: 6px;
}

.option-buttons {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.option-buttons button {
  padding: 6px 12px;
  font-size: 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
}

.option-buttons button.active {
  background: #1976d2;
  border-color: #1976d2;
  color: white;
}

.option-buttons button.use-current {
  background: #e9ecef;
  border-color: #adb5bd;
  font-size: 11px;
}

.option-input {
  display: flex;
  gap: 8px;
}

.option-input input {
  flex: 1;
  padding: 6px 10px;
  font-size: 13px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.option-input button {
  padding: 6px 10px;
  font-size: 11px;
  background: #e9ecef;
  border: 1px solid #adb5bd;
  border-radius: 4px;
  cursor: pointer;
}

.regen-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #dee2e6;
}

.regen-actions button {
  padding: 8px 14px;
  font-size: 13px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.regen-actions button.regenerate {
  background: #17a2b8;
  color: white;
}

.regen-actions button:not(.regenerate) {
  background: #e9ecef;
}

/* Debug */
.debug-section {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.debug-section summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  color: #666;
}

.debug-section pre {
  background: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 10px;
  max-height: 200px;
  margin-top: 8px;
}

/* Responsive */
@media (max-width: 1024px) {
  .main-layout {
    grid-template-columns: 1fr;
  }
}
</style>

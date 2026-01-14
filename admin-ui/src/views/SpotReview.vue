<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute()
const router = useRouter()

const spot = ref(null)
const loading = ref(true)
const saving = ref(false)
const regenerating = ref(false)
const error = ref(null)

// Regenerate options
const showRegenOptions = ref(false)
const regenPosition = ref('')  // '', 'IP', 'OOP'
const regenCombo = ref('')     // '' or specific combo like 'AhKs'

// Form data
const title = ref('')
const questionText = ref('')
const explanation = ref('')
const difficulty = ref(2)
const answerOptions = ref([])
const correctAnswer = ref('')
const tags = ref([])
const newTag = ref('')
const scheduledDate = ref('')

// Get today's date in YYYY-MM-DD format
const today = new Date().toISOString().split('T')[0]
scheduledDate.value = today

// Suggested tags based on spot
const suggestedTags = computed(() => {
  if (!spot.value) return []
  return [
    'cash', '6max', `${Math.round(spot.value.stack_size_bb)}bb`,
    'srp', spot.value.street
  ]
})

async function loadSpot(spotId) {
  loading.value = true
  error.value = null
  spot.value = null
  title.value = ''

  try {
    spot.value = await api.getSpot(spotId)
    answerOptions.value = [...spot.value.available_actions]
    correctAnswer.value = spot.value.correct_action
    tags.value = [...suggestedTags.value]
    questionText.value = `You are ${spot.value.hero_position} with ${spot.value.hero_combo}. What's your play?`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
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

function formatEV(ev, freq) {
  // Don't show EV for <1% frequency actions - the values are unreliable
  // (off-equilibrium paths in the solver tree)
  if (freq < 0.01) return '-'
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

async function approve() {
  if (!title.value || !explanation.value) {
    error.value = 'Please fill in title and explanation'
    return
  }
  if (!scheduledDate.value) {
    error.value = 'Please select a scheduled date'
    return
  }

  saving.value = true
  error.value = null

  try {
    await api.approveSpot(spot.value.id, {
      title: title.value,
      question_text: questionText.value,
      answer_options: answerOptions.value,
      correct_answer: correctAnswer.value,
      explanation: explanation.value,
      difficulty: difficulty.value,
      tags: tags.value,
      scheduled_date: scheduledDate.value,
    })
    router.push('/')
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
                <div class="hero-hand">
                  <span class="card-chip hero">{{ spot.hero_combo.slice(0,2) }}</span>
                  <span class="card-chip hero">{{ spot.hero_combo.slice(2,4) }}</span>
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

          <!-- Optimal Play Table -->
          <div class="optimal-section">
            <div class="section-label">Optimal Play</div>
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Freq</th>
                  <th>EV</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="action in spot.available_actions"
                  :key="action"
                  :class="{ correct: action === spot.correct_action }"
                >
                  <td>
                    {{ formatAction(action) }}
                    <span v-if="action === spot.correct_action" class="check">&#10003;</span>
                  </td>
                  <td>{{ formatFrequency(spot.action_frequencies[action]) }}</td>
                  <td>{{ formatEV(spot.ev_by_action[action] || 0, spot.action_frequencies[action]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- RIGHT SIDE: Question Form -->
        <div class="right-panel">
          <div class="form-section">
            <h2>Create Puzzle</h2>

            <div v-if="error" class="error">{{ error }}</div>

            <div class="form-group">
              <label>Title</label>
              <input v-model="title" placeholder="e.g., River Value Bet" />
            </div>

            <div class="form-group">
              <label>Question</label>
              <textarea v-model="questionText" rows="2"></textarea>
            </div>

            <div class="form-group">
              <label>Explanation</label>
              <textarea v-model="explanation" rows="4" placeholder="Explain why this is the correct play..."></textarea>
            </div>

            <div class="form-row form-row-3">
              <div class="form-group">
                <label>Scheduled Date</label>
                <input type="date" v-model="scheduledDate" />
              </div>

              <div class="form-group">
                <label>Correct Answer</label>
                <select v-model="correctAnswer">
                  <option v-for="opt in answerOptions" :key="opt" :value="opt">{{ opt }}</option>
                </select>
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

.form-row-3 {
  grid-template-columns: 1fr 1fr 1fr;
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

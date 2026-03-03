<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import RangeGrid from '../components/RangeGrid.vue'

const route = useRoute()
const router = useRouter()

const puzzle = ref(null)
const treeData = ref(null)
const loading = ref(true)
const saving = ref(false)
const error = ref(null)

// Range data for RangeGrid
const heroRange = ref(null)
const handOrder = ref(null)

// Form data
const questionText = ref('')
const difficulty = ref(2)
const tags = ref([])
const newTag = ref('')
const scheduledDate = ref('')

// Action data: {action: string, selected: bool, correct: bool, explanation: string}
const actionData = ref([])

// Solver data from tree
const solverActions = ref([])

// Extract board from puzzle action data
const board = computed(() => {
  if (!puzzle.value) return ''
  const action = puzzle.value.action || {}
  if (action.river?.Cards) return action.river.Cards
  if (action.turn?.Cards) return `${action.flop?.Cards || ''} ${action.turn.Cards}`.trim()
  if (action.flop?.Cards) return action.flop.Cards
  return ''
})

// Get street from data
const street = computed(() => {
  if (!puzzle.value) return 'Flop'
  const action = puzzle.value.action || {}
  if (action.river) return 'River'
  if (action.turn) return 'Turn'
  if (action.flop) return 'Flop'
  return 'Preflop'
})

// Extract hero position from puzzle (hero field is just the position like "BB" or "SB")
const heroPosition = computed(() => {
  return puzzle.value?.hero || ''
})

// Extract hero hand from action.preflop.{heroPosition}.Cards
const heroCombo = computed(() => {
  if (!puzzle.value?.action?.preflop || !heroPosition.value) return ''

  const preflop = puzzle.value.action.preflop
  const heroData = preflop[heroPosition.value]

  if (heroData?.Cards) {
    return heroData.Cards
  }

  return ''
})

// Extract villain position from action (the other position in preflop)
const villainPosition = computed(() => {
  if (!puzzle.value?.action?.preflop || !heroPosition.value) return ''

  const preflop = puzzle.value.action.preflop
  for (const pos of Object.keys(preflop)) {
    if (pos !== heroPosition.value) {
      return pos
    }
  }
  return ''
})

// Build street actions for display
const streetActions = computed(() => {
  if (!puzzle.value?.action) return []
  const action = puzzle.value.action
  const streets = []

  if (action.flop) {
    streets.push({
      street: 'Flop',
      cards: action.flop.Cards,
      actions: formatStreetActions(action.flop.Actions)
    })
  }
  if (action.turn) {
    streets.push({
      street: 'Turn',
      cards: action.turn.Cards?.slice(-2),
      actions: formatStreetActions(action.turn.Actions)
    })
  }
  if (action.river) {
    streets.push({
      street: 'River',
      cards: action.river.Cards?.slice(-2),
      actions: formatStreetActions(action.river.Actions)
    })
  }

  return streets
})

function formatStreetActions(actions) {
  if (!actions) return ''
  return actions.map(a => {
    if (a.Action === 'check') return `${a.Position} checks`
    if (a.Action === 'bet') return `${a.Position} bets ${a.Amount}bb`
    if (a.Action === 'call') return `${a.Position} calls`
    if (a.Action === 'raise') return `${a.Position} raises to ${a.Amount}bb`
    return `${a.Position} ${a.Action}`
  }).join(', ')
}

async function loadPuzzle() {
  loading.value = true
  error.value = null

  try {
    // Load the puzzle
    const puzzles = await api.getPuzzlesForDate(route.query.date)
    puzzle.value = puzzles.find(p => p.id === route.params.id)

    if (!puzzle.value) {
      error.value = 'Puzzle not found'
      return
    }

    // Initialize form from puzzle
    questionText.value = puzzle.value.question_text || ''
    difficulty.value = puzzle.value.difficulty || 2
    tags.value = [...(puzzle.value.tags || [])]
    scheduledDate.value = puzzle.value.scheduled_date || ''

    // Initialize action data from puzzle
    actionData.value = (puzzle.value.answer_options || []).map(action => ({
      action,
      selected: true,
      correct: puzzle.value.correct_answers?.includes(action) || false,
      explanation: puzzle.value.explanations?.[action] || ''
    }))

    // Load tree data for solver context
    treeData.value = await api.getPuzzleTreeData(puzzle.value.id)

    // Load range data if we have tree
    if (treeData.value?.has_tree) {
      await loadRangeData()
      await loadSolverActions()
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

async function loadRangeData() {
  if (!treeData.value?.sim_id || !treeData.value?.tree_path) return

  try {
    // Fetch hand order (cached after first load)
    if (!handOrder.value) {
      handOrder.value = await api.getHandOrder()
    }

    // Fetch ranges at this tree path
    const rangeData = await api.getTreeRanges(treeData.value.sim_id, treeData.value.tree_path)

    // Determine which range is hero's based on position
    const heroIsOOP = heroPosition.value === 'BB' || heroPosition.value === 'SB'
    heroRange.value = heroIsOOP ? rangeData.oop_range : rangeData.ip_range
  } catch (e) {
    console.error('Failed to load range data:', e)
  }
}

async function loadSolverActions() {
  if (!treeData.value?.sim_id || !treeData.value?.tree_path) return

  try {
    const nodeData = await api.getTreeActions(treeData.value.sim_id, treeData.value.tree_path)
    solverActions.value = nodeData.actions || []
  } catch (e) {
    console.error('Failed to load solver actions:', e)
  }
}

function formatFrequency(freq) {
  if (freq === undefined) return '-'
  return `${(freq * 100).toFixed(0)}%`
}

function formatEV(ev) {
  if (ev === undefined) return '-'
  return ev >= 0 ? `+${ev.toFixed(2)}bb` : `${ev.toFixed(2)}bb`
}

function addTag() {
  if (newTag.value && !tags.value.includes(newTag.value)) {
    tags.value.push(newTag.value.trim().toLowerCase())
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

async function save() {
  if (correctActions.value.length === 0) {
    error.value = 'Please mark at least one answer as correct'
    return
  }

  saving.value = true
  error.value = null

  try {
    await api.updatePuzzle(puzzle.value.id, {
      question_text: questionText.value,
      answer_options: selectedActions.value,
      correct_answers: correctActions.value,
      explanations: explanationsMap.value,
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

function cancel() {
  router.push('/')
}

onMounted(loadPuzzle)
</script>

<template>
  <div class="puzzle-review">
    <div v-if="loading" class="loading">Loading puzzle...</div>
    <div v-else-if="error && !puzzle" class="error">{{ error }}</div>
    <template v-else-if="puzzle">
      <div class="main-layout">
        <!-- LEFT SIDE: Puzzle Details -->
        <div class="left-panel">
          <!-- Top Row: Board + Hero side by side -->
          <div class="top-row">
            <div class="board-section">
              <div class="section-label">Board</div>
              <div class="board-cards">
                <span v-for="(card, i) in board.match(/.{2}/g)" :key="i" class="card-chip">
                  {{ card }}
                </span>
              </div>
            </div>
            <div class="hero-section">
              <div class="hero-label">HERO</div>
              <div class="hero-info">
                <span class="hero-position">{{ heroPosition }}</span>
                <div v-if="heroCombo" class="hero-hand">
                  <span class="card-chip hero">{{ heroCombo.slice(0,2) }}</span>
                  <span class="card-chip hero">{{ heroCombo.slice(2,4) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Game Info Row -->
          <div class="info-row">
            <div class="info-item">
              <span class="info-label">Pot</span>
              <span class="info-value">{{ puzzle.pot_size_at_decision }}bb</span>
            </div>
            <div class="info-item">
              <span class="info-label">Street</span>
              <span class="info-value">{{ street }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Villain</span>
              <span class="info-value">{{ villainPosition || 'N/A' }}</span>
            </div>
          </div>

          <!-- Hand History -->
          <div v-if="streetActions.length" class="history-section">
            <div class="section-label">Action</div>
            <div class="street-rows">
              <div
                v-for="(streetAction, i) in streetActions"
                :key="i"
                class="street-row"
                :class="{ 'decision-street': streetAction.street === street }"
              >
                <span class="street-name">{{ streetAction.street }}</span>
                <span v-if="streetAction.cards" class="street-cards">{{ streetAction.cards }}</span>
                <span class="street-actions">{{ streetAction.actions }}</span>
              </div>
            </div>
          </div>

          <!-- Solver Frequencies -->
          <div class="optimal-section">
            <div class="section-label">Solver Data</div>
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
                  v-for="option in puzzle.answer_options"
                  :key="option"
                  :class="{ correct: puzzle.correct_answers?.includes(option) }"
                >
                  <td>
                    {{ option }}
                    <span v-if="puzzle.correct_answers?.includes(option)" class="check">&#10003;</span>
                  </td>
                  <td>{{ formatFrequency(puzzle.action_frequencies?.[option]) }}</td>
                  <td>{{ formatEV(puzzle.ev_by_action?.[option]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Hero's Range at Decision Point -->
          <div v-if="heroRange && handOrder" class="range-section">
            <div class="section-label">Hero's Range ({{ heroPosition }})</div>
            <RangeGrid
              :range="heroRange"
              :hand-order="handOrder"
              :board="board"
              :hero-combo="heroCombo"
              :clickable="false"
            />
          </div>
          <div v-else-if="!treeData?.has_tree" class="no-tree-notice">
            Solver data not available for this puzzle.
          </div>
        </div>

        <!-- RIGHT SIDE: Edit Form -->
        <div class="right-panel">
          <div class="form-section">
            <h2>Edit Puzzle</h2>

            <div v-if="error" class="error">{{ error }}</div>

            <div class="form-group">
              <label>Question</label>
              <textarea v-model="questionText" rows="2"></textarea>
            </div>

            <!-- Answer Options with Correct/Explanation -->
            <div class="form-group answers-section">
              <label>Answer Options ({{ correctActions.length }} correct)</label>
              <div class="answer-cards">
                <div
                  v-for="(actionItem, index) in actionData"
                  :key="actionItem.action"
                  class="answer-card"
                  :class="{ 'is-correct': actionItem.correct }"
                >
                  <div class="answer-header">
                    <label class="correct-checkbox">
                      <input
                        type="checkbox"
                        :checked="actionItem.correct"
                        @change="actionData[index].correct = $event.target.checked"
                      />
                      <span class="answer-action">{{ actionItem.action }}</span>
                      <span v-if="actionItem.correct" class="correct-badge">Correct</span>
                    </label>
                    <span class="answer-freq">{{ formatFrequency(puzzle.action_frequencies?.[actionItem.action]) }}</span>
                  </div>
                  <textarea
                    v-model="actionData[index].explanation"
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
              <button class="primary" @click="save" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save Changes' }}
              </button>
              <button @click="cancel" :disabled="saving">Cancel</button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.puzzle-review {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
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

.range-section {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.no-tree-notice {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  color: #666;
  font-size: 14px;
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
  box-sizing: border-box;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
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

.action-buttons button.primary:hover {
  background: #1565c0;
}

.action-buttons button:not(.primary) {
  background: #e9ecef;
}

.action-buttons button:not(.primary):hover {
  background: #dee2e6;
}

.loading {
  padding: 40px;
  text-align: center;
  color: #666;
}

.error {
  padding: 12px;
  background: #ffebee;
  color: #c62828;
  border-radius: 6px;
  margin-bottom: 16px;
}

/* Responsive */
@media (max-width: 1024px) {
  .main-layout {
    grid-template-columns: 1fr;
  }
}
</style>

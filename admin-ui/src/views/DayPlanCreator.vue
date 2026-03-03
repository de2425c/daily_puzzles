<script setup>
import { ref, onMounted, computed, watch, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref(null)
const dayPlan = ref(null)

// Import modal
const showImportModal = ref(false)
const importJson = ref('')
const importLoading = ref(false)
const importError = ref(null)
const importResult = ref(null)

// Preflop data
const rfiPositions = ref([])

// Per-config local state (preflop selection before locking)
const configForms = ref([createConfigForm(), createConfigForm()])

// Per-slot local state keyed by slot ID
const slotForms = reactive({})

// Combo detail modal state
const comboDetailModal = reactive({
  visible: false,
  handKey: '',
  combos: []
})

const scheduledDate = computed(() => route.params.date)

// ---- Constants ----
const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
const SUITS = ['s', 'h', 'd', 'c']
const SUIT_SYMBOLS = { s: '\u2660', h: '\u2665', d: '\u2666', c: '\u2663' }
const SUIT_COLORS = { s: '#000', h: '#e53935', d: '#1976d2', c: '#388e3c' }

// ---- Action logic ----
function getValidTokensForAction(actions, actionIdx) {
  if (actionIdx === 0) return ['check', 'bet', 'bet33', 'bet75', 'bet125']
  const prev = actions[actionIdx - 1]
  if (!prev) return ['check', 'bet', 'bet33', 'bet75', 'bet125']
  const prevToken = prev.token
  if (prevToken === 'check') return ['check', 'bet', 'bet33', 'bet75', 'bet125']
  return ['call', 'raise', 'allin']
}

function getActingPosition(actionIdx, ipPos, oopPos) {
  return actionIdx % 2 === 0 ? oopPos : ipPos
}

function isActionSequenceValid(actions) {
  if (actions.length === 0) return true
  const last = actions[actions.length - 1].token
  if (last === 'call') return false
  if (actions.length >= 2) {
    const secondLast = actions[actions.length - 2].token
    if (last === 'check' && secondLast === 'check') return false
  }
  return true
}

function canAddAction(actions) {
  if (actions.length === 0) return true
  return isActionSequenceValid(actions)
}

// ---- Config form (preflop selection) ----

function createConfigForm() {
  return {
    preflopPath: [],
    preflopChildren: [],
    preflopLoading: false,
    scenario: null,
    locked: false,
    locking: false,
  }
}

async function loadRfiPositions() {
  try {
    rfiPositions.value = await api.getPreflopPositions()
  } catch (e) {
    console.error('Failed to load preflop positions:', e)
  }
}

async function onSelectRfiPosition(cf, position) {
  const rfiName = position + '_RFI'
  cf.preflopPath = [rfiName]
  cf.scenario = null
  cf.preflopLoading = true
  try {
    cf.preflopChildren = await api.getPreflopChildren([rfiName])
  } catch (e) {
    cf.preflopChildren = []
  }
  cf.preflopLoading = false
  await maybeFetchScenario(cf)
}

async function onSelectPreflopChild(cf, childName) {
  cf.preflopPath.push(childName)
  cf.scenario = null
  cf.preflopLoading = true
  try {
    cf.preflopChildren = await api.getPreflopChildren(cf.preflopPath)
  } catch (e) {
    cf.preflopChildren = []
  }
  cf.preflopLoading = false
  await maybeFetchScenario(cf)
}

async function maybeFetchScenario(cf) {
  if (cf.preflopPath.length >= 2 && cf.preflopChildren.length === 0 && !cf.preflopLoading) {
    try {
      cf.scenario = await api.getPreflopScenario(cf.preflopPath)
    } catch (e) {
      console.error('Failed to fetch scenario:', e)
    }
  }
}

function resetPreflop(cf) {
  cf.preflopPath = []
  cf.preflopChildren = []
  cf.scenario = null
}

function removePreflopStep(cf, idx) {
  cf.preflopPath = cf.preflopPath.slice(0, idx)
  cf.scenario = null
  if (cf.preflopPath.length === 0) {
    cf.preflopChildren = []
  } else {
    cf.preflopLoading = true
    api.getPreflopChildren(cf.preflopPath).then(async children => {
      cf.preflopChildren = children
      cf.preflopLoading = false
      await maybeFetchScenario(cf)
    }).catch(() => {
      cf.preflopChildren = []
      cf.preflopLoading = false
    })
  }
}

// ---- Lock preflop (create plan + set config) ----

async function lockConfig(cf, configIdx) {
  if (!cf.scenario) return
  cf.locking = true
  error.value = null
  try {
    // Create plan if needed
    if (!dayPlan.value) {
      dayPlan.value = await api.createDayPlan(scheduledDate.value)
    }
    // Set preflop config
    dayPlan.value = await api.setPreflopConfig(dayPlan.value.id, configIdx, cf.preflopPath)
    cf.locked = true
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    cf.locking = false
  }
}

async function unlockConfig(cf, configIdx) {
  if (!dayPlan.value) return
  cf.locking = true
  error.value = null
  try {
    dayPlan.value = await api.deletePreflopConfig(dayPlan.value.id, configIdx)
    // Reset local form
    cf.preflopPath = []
    cf.preflopChildren = []
    cf.scenario = null
    cf.locked = false
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    cf.locking = false
  }
}

// ---- Slot form helpers ----

function getSlotForm(slotId) {
  if (!slotForms[slotId]) {
    slotForms[slotId] = {
      cards: [],
      pickingCard: false,
      actions: [],
      heroPos: '',
      running: false,
      runError: null,
      nodeInfo: null,       // {position, actions: [{label, token, freq}], range_grid}
      nodeInfoLoading: false,
      comboInput: '',       // e.g. "AsKh"
      // Inline puzzle review fields
      puzzleData: null,
      puzzleLoading: false,
      actionSelections: [],  // [{action, selected, correct, explanation, freq, ev}]
      difficulty: 2,
      puzzleSaving: false,
      puzzleSaved: false,
    }
  }
  return slotForms[slotId]
}

function slotCards(config, slot) {
  // Get all cards used in this config's slots (from server state + local forms)
  const used = new Set()
  for (const s of config.slots) {
    if (s.board) {
      for (let i = 0; i < s.board.length; i += 2) used.add(s.board.substring(i, i + 2))
    }
    if (s.id !== slot.id) {
      const sf = slotForms[s.id]
      if (sf) for (const c of sf.cards) used.add(c)
    }
  }
  return used
}

function maxCards(slot) {
  return slot.street === 'flop' ? 3 : 1
}

function toggleCard(slot, card, config) {
  const sf = getSlotForm(slot.id)
  const idx = sf.cards.indexOf(card)
  if (idx >= 0) {
    sf.cards.splice(idx, 1)
  } else if (sf.cards.length < maxCards(slot)) {
    sf.cards.push(card)
    if (sf.cards.length >= maxCards(slot)) sf.pickingCard = false
  }
}

function isCardDisabled(card, slot, config) {
  const sf = getSlotForm(slot.id)
  if (sf.cards.includes(card)) return false
  return slotCards(config, slot).has(card)
}

function formatCard(card) {
  return card[0] + SUIT_SYMBOLS[card[1]]
}

function addAction(slot) {
  const sf = getSlotForm(slot.id)
  const validTokens = getValidTokensForAction(sf.actions, sf.actions.length)
  sf.actions.push({ token: validTokens[0], isHeroDecision: false })
  fetchNodeInfo(slot)
}

function removeAction(slot, idx) {
  const sf = getSlotForm(slot.id)
  sf.actions.splice(idx)
  fetchNodeInfo(slot)
}

function onHeroDecisionChange(slot, actionIdx) {
  const sf = getSlotForm(slot.id)
  if (sf.actions[actionIdx].isHeroDecision) {
    sf.actions.forEach((x, xi) => { if (xi !== actionIdx) x.isHeroDecision = false })
  }
  fetchNodeInfo(slot)
}

function onActionTokenChange(slot, actionIdx) {
  const sf = getSlotForm(slot.id)
  if (actionIdx < sf.actions.length - 1) sf.actions.splice(actionIdx + 1)
  fetchNodeInfo(slot)
}

async function fetchNodeInfo(slot) {
  if (!dayPlan.value) return
  const sf = getSlotForm(slot.id)
  const line = sf.actions.map(a => a.token)
  sf.nodeInfoLoading = true
  try {
    sf.nodeInfo = await api.getNodeInfo(dayPlan.value.id, slot.id, line)
  } catch (e) {
    sf.nodeInfo = null
  } finally {
    sf.nodeInfoLoading = false
  }
}

// ---- Range grid helpers ----

function getRangeCellLabel(ri, ci) {
  if (ri === ci) return RANKS[ri] + RANKS[ci] // pair
  if (ri < ci) return RANKS[ri] + RANKS[ci] + 's' // suited (above diagonal)
  return RANKS[ci] + RANKS[ri] + 'o' // offsuit (below diagonal)
}

function getRangeCell(slot, ri, ci) {
  const sf = getSlotForm(slot.id)
  if (!sf.nodeInfo || !sf.nodeInfo.range_grid) return { weight: 0 }
  const label = getRangeCellLabel(ri, ci)
  const cell = sf.nodeInfo.range_grid[label]
  if (!cell) return { weight: 0 }
  return cell
}

function getRangeCellTooltip(slot, ri, ci) {
  const cell = getRangeCell(slot, ri, ci)
  if (!cell || !cell.weight) return ''
  const label = getRangeCellLabel(ri, ci)
  let tip = `${label}: ${(cell.weight * 100).toFixed(0)}%`
  if (cell.actions) {
    for (const [action, freq] of Object.entries(cell.actions)) {
      tip += `\n  ${action}: ${(freq * 100).toFixed(0)}%`
    }
  }
  return tip
}

// Combo detail modal functions
function openComboDetail(slot, ri, ci) {
  const sf = getSlotForm(slot.id)
  if (!sf.nodeInfo || !sf.nodeInfo.combo_details) return
  const label = getRangeCellLabel(ri, ci)
  const combos = sf.nodeInfo.combo_details[label]
  if (!combos || combos.length === 0) return
  comboDetailModal.handKey = label
  comboDetailModal.combos = combos
  comboDetailModal.visible = true
}

function closeComboDetail() {
  comboDetailModal.visible = false
  comboDetailModal.handKey = ''
  comboDetailModal.combos = []
}

function formatComboWithSuits(combo) {
  // Convert "Js9s" to colored suit symbols
  // combo format: "Js9s" (rank+suit+rank+suit)
  if (!combo || combo.length !== 4) return combo
  const r1 = combo[0]
  const s1 = combo[1]
  const r2 = combo[2]
  const s2 = combo[3]
  return [
    { rank: r1, suit: s1, symbol: SUIT_SYMBOLS[s1], color: SUIT_COLORS[s1] },
    { rank: r2, suit: s2, symbol: SUIT_SYMBOLS[s2], color: SUIT_COLORS[s2] }
  ]
}

// ---- Per-slot sim ----

function boardForSlot(config, slot) {
  // For flop: just the 3 cards picked. For turn/river: parent board + new card.
  const sf = getSlotForm(slot.id)
  if (slot.street === 'flop') {
    return sf.cards.join('')
  }
  // Find parent slot's board
  const parent = config.slots.find(s => s.id === slot.parent_slot_id)
  if (parent && parent.board) {
    return parent.board + sf.cards.join('')
  }
  return sf.cards.join('')
}

async function runSlotSim(config, slot) {
  const sf = getSlotForm(slot.id)
  sf.running = true
  sf.runError = null
  error.value = null

  try {
    if (slot.street === 'flop') {
      const board = sf.cards.join('')
      dayPlan.value = await api.createSlotSim(dayPlan.value.id, slot.id, { board })
    } else {
      // Child sim: need parent's action_path
      const parent = config.slots.find(s => s.id === slot.parent_slot_id)
      if (!parent || !parent.action_path) {
        sf.runError = 'Parent slot has no action_path. Make sure the parent line resolves the street.'
        sf.running = false
        return
      }
      const card = sf.cards[0]
      dayPlan.value = await api.createChildSlotSim(dayPlan.value.id, slot.id, {
        actionPath: parent.action_path, card,
      })
    }
    // Fetch initial node info for the root of the tree
    await fetchNodeInfo(slot)
  } catch (e) {
    sf.runError = e.response?.data?.detail || e.message
  } finally {
    sf.running = false
  }
}

async function walkAndPick(slot) {
  const sf = getSlotForm(slot.id)
  const line = sf.actions.map(a => a.token)
  const decisionIdx = sf.actions.findIndex(a => a.isHeroDecision)
  const combo = sf.comboInput.trim()

  if (line.length === 0) {
    sf.runError = 'Add at least one action to the line.'
    return
  }
  if (decisionIdx < 0) {
    sf.runError = 'Mark a hero decision point.'
    return
  }
  if (combo.length !== 4) {
    sf.runError = 'Enter a 4-character combo (e.g. AsKh).'
    return
  }

  sf.running = true
  sf.runError = null
  error.value = null

  try {
    // Walk line first to set tree_path, action_path, top_combos
    dayPlan.value = await api.walkLine(dayPlan.value.id, slot.id, { line, decisionIdx })
    // Then pick the combo
    dayPlan.value = await api.pickCombo(dayPlan.value.id, slot.id, combo)
    // Invalidate puzzle cache and load puzzle data for the now-complete slot

    const updatedSlot = dayPlan.value.configs
      .flatMap(c => c.slots)
      .find(s => s.id === slot.id)
    if (updatedSlot && updatedSlot.puzzle_id) {
      await loadPuzzleData(updatedSlot)
    }
  } catch (e) {
    sf.runError = e.response?.data?.detail || e.message
  } finally {
    sf.running = false
  }
}

async function onResetSlot(slot) {
  error.value = null
  try {
    dayPlan.value = await api.resetSlot(dayPlan.value.id, slot.id)
    // Reset local form
    delete slotForms[slot.id]

  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

async function onRepickSlot(slot) {
  error.value = null
  try {
    dayPlan.value = await api.repickSlot(dayPlan.value.id, slot.id)
    // Reset puzzle data in local form but keep other state
    const sf = getSlotForm(slot.id)
    sf.puzzleData = null
    sf.puzzleSaved = false
    sf.actionSelections = []
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

// ---- Inline puzzle review ----

async function loadPuzzleData(slot) {
  if (!slot.puzzle_id) return
  const sf = getSlotForm(slot.id)
  if (sf.puzzleData) return // already loaded
  sf.puzzleLoading = true
  try {
    const puzzle = await api.getPuzzleById(slot.puzzle_id)
    if (!puzzle) { sf.puzzleLoading = false; return }
    sf.puzzleData = puzzle
    sf.difficulty = puzzle.difficulty || 2

    // Build action selections from puzzle data
    const allActions = Object.keys(puzzle.action_frequencies || {})
    sf.actionSelections = allActions.map(action => ({
      action,
      selected: (puzzle.answer_options || []).includes(action),
      correct: (puzzle.correct_answers || []).includes(action),
      explanation: puzzle.explanations?.[action] || '',
      freq: puzzle.action_frequencies?.[action],
      ev: puzzle.ev_by_action?.[action],
    }))

    // Check if puzzle was previously saved (has correct_answers set)
    sf.puzzleSaved = (puzzle.correct_answers || []).length > 0
  } catch (e) {
    console.error('Failed to load puzzle data:', e)
  } finally {
    sf.puzzleLoading = false
  }
}

function getSlotOrder(slot) {
  if (!dayPlan.value?.configs) return null
  let idx = 1
  for (const config of dayPlan.value.configs) {
    for (const s of config.slots) {
      if (s.id === slot.id) return idx
      idx++
    }
  }
  return null
}

async function savePuzzleForSlot(slot) {
  const sf = getSlotForm(slot.id)
  if (!slot.puzzle_id) return
  sf.puzzleSaving = true
  try {
    const selected = sf.actionSelections.filter(a => a.selected)
    const answerOptions = selected.map(a => a.action)
    const correctAnswers = selected.filter(a => a.correct).map(a => a.action)
    const explanations = {}
    selected.forEach(a => { explanations[a.action] = a.explanation })

    await api.updatePuzzle(slot.puzzle_id, {
      answer_options: answerOptions,
      correct_answers: correctAnswers,
      explanations,
      difficulty: sf.difficulty,
      order: getSlotOrder(slot),
    })
    sf.puzzleSaved = true
    // Invalidate cache so next load gets fresh data

  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    sf.puzzleSaving = false
  }
}

function formatFrequency(freq) {
  if (freq === undefined || freq === null) return '-'
  return `${(freq * 100).toFixed(0)}%`
}

function formatEV(ev) {
  if (ev === undefined || ev === null) return '-'
  return ev >= 0 ? `+${ev.toFixed(2)}bb` : `${ev.toFixed(2)}bb`
}

// ---- Helpers ----

function getConfigData(configIdx) {
  if (!dayPlan.value?.configs) return null
  // Try exact index first
  if (dayPlan.value.configs[configIdx]) return dayPlan.value.configs[configIdx]
  // Fallback: match by preflop path
  const cf = configForms.value[configIdx]
  if (cf && cf.preflopPath.length > 0) {
    const pathStr = cf.preflopPath.join(',')
    return dayPlan.value.configs.find(c => c.preflop_path.join(',') === pathStr) || null
  }
  return null
}

function getSlotData(configIdx, slotId) {
  const config = getConfigData(configIdx)
  if (!config) return null
  return config.slots.find(s => s.id === slotId)
}

// Which slots should be visible? A slot is visible if:
// - It's a flop slot, OR
// - Its parent is complete (combo picked)
function visibleSlots(config) {
  if (!config) return []
  return config.slots.filter(slot => {
    if (slot.street === 'flop') return true
    // Show turn/river only if parent is complete
    const parent = config.slots.find(s => s.id === slot.parent_slot_id)
    return parent && parent.status === 'complete'
  })
}

function slotLabel(slot, config) {
  const streetName = slot.street.charAt(0).toUpperCase() + slot.street.slice(1)
  if (!config) return streetName
  const idx = config.slots.indexOf(slot)
  // Slots: [flop1, turn1, flop2, turn2, river]
  // Board 1 (flop+turn): indices 0, 1
  // Board 2 (flop+turn+river): indices 2, 3, 4
  if (idx <= 1) return `Board 1 — ${streetName}`
  return `Board 2 — ${streetName}`
}

function slotHint(slot, config) {
  if (!config) return ''
  const idx = config.slots.indexOf(slot)
  if (idx === 0) return 'Flop + Turn only'
  if (idx === 2) return 'Flop + Turn + River'
  return ''
}

function heroPositionOptions(config) {
  if (!config) return []
  return [config.ip_position, config.oop_position]
}

const completedSlots = computed(() => {
  if (!dayPlan.value?.configs) return 0
  return dayPlan.value.configs.reduce((a, c) => a + c.slots.filter(s => s.status === 'complete').length, 0)
})

const totalSlots = computed(() => {
  if (!dayPlan.value?.configs) return 0
  return dayPlan.value.configs.reduce((a, c) => a + c.slots.length, 0)
})

function formatDate(dateStr) {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
}

function goHome() { router.push('/') }

// ---- Day plan loading ----

async function loadDayPlan() {
  loading.value = true
  error.value = null
  try {
    dayPlan.value = await api.getDayPlan(scheduledDate.value)
    // Restore config forms from loaded plan
    if (dayPlan.value?.configs) {
      for (let i = 0; i < dayPlan.value.configs.length; i++) {
        const config = dayPlan.value.configs[i]
        if (config && configForms.value[i]) {
          configForms.value[i].preflopPath = config.preflop_path || []
          configForms.value[i].locked = true
          // Try to load scenario
          try {
            configForms.value[i].scenario = await api.getPreflopScenario(config.preflop_path)
          } catch (e) { /* ok */ }
        }
      }
    }
    // Load puzzle data for already-complete slots
    if (dayPlan.value?.configs) {
      for (const config of dayPlan.value.configs) {
        for (const slot of config.slots) {
          if (slot.status === 'complete' && slot.puzzle_id) {
            await loadPuzzleData(slot)
          }
        }
      }
    }
  } catch (e) {
    // 404 means no plan yet, that's fine
    if (e.response?.status !== 404) {
      error.value = e.message
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadDayPlan(), loadRfiPositions()])
})

watch(() => route.params.date, () => loadDayPlan())

// ---- Import JSON ----

async function doImport() {
  importLoading.value = true
  importError.value = null
  importResult.value = null
  try {
    const parsed = JSON.parse(importJson.value)
    parsed.date = scheduledDate.value
    const result = await api.importDayPlan(parsed)
    importResult.value = result
    dayPlan.value = result.day_plan
    if (result.errors.length === 0) {
      showImportModal.value = false
      importJson.value = ''
    }
  } catch (e) {
    importError.value = e.response?.data?.detail || e.message
  } finally {
    importLoading.value = false
  }
}
</script>

<template>
  <div class="day-plan-creator">
    <header class="page-header">
      <button class="back-btn" @click="goHome">&larr; Back</button>
      <div class="header-content">
        <h1>Day Plan: {{ formatDate(scheduledDate) }}</h1>
        <div class="header-actions">
          <button class="import-btn" @click="showImportModal = true">Import JSON</button>
          <div v-if="dayPlan" class="progress-badge">{{ completedSlots }} / {{ totalSlots }} slots complete</div>
        </div>
      </div>
    </header>

    <div v-if="loading" class="loading">Loading day plan...</div>
    <div v-if="error" class="error">{{ error }}</div>

    <template v-if="!loading">
      <!-- Two config sections -->
      <div v-for="(cf, ci) in configForms" :key="ci" class="config-section">
        <div class="config-section-header" @click="cf._collapsed = !cf._collapsed">
          <h2>Config {{ ci + 1 }}</h2>
          <span v-if="getConfigData(ci)" class="config-desc">{{ getConfigData(ci).description }}</span>
          <span v-if="cf.locked" class="locked-badge">Locked</span>
          <button v-if="cf.locked" class="unlock-btn" :disabled="cf.locking" @click.stop="unlockConfig(cf, ci)">Unlock</button>
        </div>

        <div v-if="!cf._collapsed" class="config-section-body">
          <!-- Preflop selection (only if not locked) -->
          <div v-if="!cf.locked" class="preflop-builder">
            <label class="field-label">Preflop:</label>
            <div class="preflop-steps">
              <span
                v-for="(step, idx) in cf.preflopPath"
                :key="idx"
                class="path-chip"
                @click="removePreflopStep(cf, idx)"
                title="Click to remove"
              >{{ step }} &times;</span>

              <select
                v-if="cf.preflopPath.length === 0"
                class="preflop-select"
                @change="onSelectRfiPosition(cf, $event.target.value); $event.target.value = ''"
              >
                <option value="" disabled selected>Position...</option>
                <option v-for="pos in rfiPositions" :key="pos" :value="pos">{{ pos }}</option>
              </select>

              <select
                v-else-if="cf.preflopChildren.length > 0"
                class="preflop-select"
                :disabled="cf.preflopLoading"
                @change="onSelectPreflopChild(cf, $event.target.value); $event.target.value = ''"
              >
                <option value="" disabled selected>{{ cf.preflopLoading ? 'Loading...' : 'Next action...' }}</option>
                <option v-for="child in cf.preflopChildren" :key="child.name" :value="child.name">
                  {{ child.name }} ({{ child.action }}{{ child.size ? ' ' + child.size + 'bb' : '' }})
                </option>
              </select>

              <span v-else-if="cf.preflopPath.length > 0 && !cf.preflopLoading && cf.scenario" class="path-done">Ready</span>
              <span v-else-if="cf.preflopLoading" class="path-loading">Loading...</span>
            </div>
            <button v-if="cf.preflopPath.length > 0" class="reset-link" @click="resetPreflop(cf)">Reset</button>

            <button
              v-if="cf.scenario && !cf.locked"
              class="lock-btn"
              :disabled="cf.locking"
              @click="lockConfig(cf, ci)"
            >{{ cf.locking ? 'Locking...' : 'Lock' }}</button>
          </div>

          <!-- Scenario info -->
          <div v-if="cf.scenario" class="scenario-info">
            <span class="scenario-desc">{{ cf.scenario.preflop_description }}</span>
            <span class="scenario-positions">
              IP: <strong>{{ cf.scenario.ip_position }}</strong>
              OOP: <strong>{{ cf.scenario.oop_position }}</strong>
              | Pot: {{ cf.scenario.pot_size_bb }}bb
            </span>
          </div>

          <!-- Slots (only when locked / config exists) -->
          <template v-if="cf.locked && getConfigData(ci)">
            <div
              v-for="slot in visibleSlots(getConfigData(ci))"
              :key="slot.id"
              class="slot-panel"
            >
              <div class="slot-header">
                <span class="slot-label">{{ slotLabel(slot, getConfigData(ci)) }}</span>
                <span v-if="slotHint(slot, getConfigData(ci))" class="slot-hint">{{ slotHint(slot, getConfigData(ci)) }}</span>
                <span v-if="slot.board" class="slot-board">{{ slot.board }}</span>
                <span class="slot-status" :class="'status-' + slot.status">{{ slot.status }}</span>
                <button v-if="slot.status !== 'empty'" class="reset-link" @click="onResetSlot(slot)">Reset</button>
              </div>

              <!-- Empty slot: pick cards and run sim -->
              <template v-if="slot.status === 'empty'">
                <div class="slot-form">
                  <!-- Card picker -->
                  <div class="card-field">
                    <span class="field-label-sm">{{ slot.street === 'flop' ? 'Board (3 cards):' : 'Card:' }}</span>
                    <div class="selected-cards">
                      <span
                        v-for="card in getSlotForm(slot.id).cards"
                        :key="card"
                        class="card-chip"
                        :style="{ color: SUIT_COLORS[card[1]] }"
                        @click="toggleCard(slot, card, getConfigData(ci))"
                      >{{ formatCard(card) }}</span>
                      <button
                        v-if="getSlotForm(slot.id).cards.length < maxCards(slot)"
                        class="pick-card-btn"
                        @click="getSlotForm(slot.id).pickingCard = !getSlotForm(slot.id).pickingCard"
                      >{{ getSlotForm(slot.id).pickingCard ? 'Done' : '+ Pick' }}</button>
                    </div>
                  </div>

                  <div v-if="getSlotForm(slot.id).pickingCard" class="card-grid">
                    <template v-for="suit in SUITS" :key="suit">
                      <button
                        v-for="rank in RANKS"
                        :key="rank + suit"
                        class="card-cell"
                        :class="{ selected: getSlotForm(slot.id).cards.includes(rank + suit), disabled: isCardDisabled(rank + suit, slot, getConfigData(ci)) }"
                        :style="{ color: SUIT_COLORS[suit] }"
                        :disabled="isCardDisabled(rank + suit, slot, getConfigData(ci)) && !getSlotForm(slot.id).cards.includes(rank + suit)"
                        @click="toggleCard(slot, rank + suit, getConfigData(ci))"
                      >{{ rank }}{{ SUIT_SYMBOLS[suit] }}</button>
                    </template>
                  </div>

                  <!-- Run Sim button -->
                  <div class="slot-actions">
                    <button
                      class="run-btn"
                      :disabled="getSlotForm(slot.id).running || getSlotForm(slot.id).cards.length < maxCards(slot)"
                      @click="runSlotSim(getConfigData(ci), slot)"
                    >
                      {{ getSlotForm(slot.id).running ? 'Running...' : 'Run Sim' }}
                    </button>
                    <div v-if="getSlotForm(slot.id).runError" class="slot-error">{{ getSlotForm(slot.id).runError }}</div>
                  </div>
                </div>
              </template>

              <!-- sim_ready: build action line with GTO freqs, then pick combo -->
              <template v-else-if="slot.status === 'sim_ready'">
                <div class="slot-form">
                  <!-- GTO action frequencies at current node -->
                  <div v-if="getSlotForm(slot.id).nodeInfo && !getSlotForm(slot.id).nodeInfo.is_terminal" class="node-info-bar">
                    <span class="node-position">{{ getSlotForm(slot.id).nodeInfo.position }} acts:</span>
                    <span
                      v-for="act in getSlotForm(slot.id).nodeInfo.actions"
                      :key="act.label"
                      class="node-action-freq"
                    >{{ act.label }} <strong>{{ (act.freq * 100).toFixed(0) }}%</strong></span>
                  </div>
                  <div v-if="getSlotForm(slot.id).nodeInfo && getSlotForm(slot.id).nodeInfo.is_terminal" class="action-terminal">
                    Terminal node reached
                  </div>
                  <div v-if="getSlotForm(slot.id).nodeInfoLoading" class="path-loading">Loading node info...</div>

                  <!-- Hero position -->
                  <div class="inline-field">
                    <span class="field-label-sm">Hero:</span>
                    <select v-model="getSlotForm(slot.id).heroPos" class="select-input-sm">
                      <option v-for="pos in heroPositionOptions(getConfigData(ci))" :key="pos" :value="pos">{{ pos }}</option>
                    </select>
                  </div>

                  <!-- Action line -->
                  <div class="actions-field">
                    <span class="field-label-sm">Line:</span>
                    <div class="action-list">
                      <div v-for="(a, ai) in getSlotForm(slot.id).actions" :key="ai" class="action-item">
                        <span class="action-position" :class="{ 'is-hero': getActingPosition(ai, getConfigData(ci).ip_position, getConfigData(ci).oop_position) === getSlotForm(slot.id).heroPos }">
                          {{ getActingPosition(ai, getConfigData(ci).ip_position, getConfigData(ci).oop_position) }}
                        </span>
                        <select
                          v-model="a.token"
                          class="action-select"
                          @change="onActionTokenChange(slot, ai)"
                        >
                          <option
                            v-for="t in getValidTokensForAction(getSlotForm(slot.id).actions, ai)"
                            :key="t"
                            :value="t"
                          >{{ t }}</option>
                        </select>
                        <label class="hero-check">
                          <input
                            type="checkbox"
                            v-model="a.isHeroDecision"
                            @change="onHeroDecisionChange(slot, ai)"
                            :disabled="getActingPosition(ai, getConfigData(ci).ip_position, getConfigData(ci).oop_position) !== getSlotForm(slot.id).heroPos"
                          />
                          Decision
                        </label>
                        <button class="remove-btn-tiny" @click="removeAction(slot, ai)">&times;</button>
                      </div>
                      <button
                        v-if="canAddAction(getSlotForm(slot.id).actions) && !(getSlotForm(slot.id).nodeInfo && getSlotForm(slot.id).nodeInfo.is_terminal)"
                        class="add-action-btn"
                        @click="addAction(slot)"
                      >+ Action</button>
                      <div v-if="getSlotForm(slot.id).actions.length > 0 && !canAddAction(getSlotForm(slot.id).actions)" class="action-terminal">
                        Street complete
                      </div>
                    </div>
                  </div>

                  <!-- Range grid at decision point -->
                  <div v-if="getSlotForm(slot.id).nodeInfo && getSlotForm(slot.id).nodeInfo.range_grid" class="range-grid-section">
                    <div class="range-grid-header">Range at current node <span class="range-grid-hint">(click cell for suit breakdown)</span></div>
                    <div class="range-grid-13x13">
                      <template v-for="(row, ri) in RANKS" :key="ri">
                        <div
                          v-for="(col, ci2) in RANKS"
                          :key="ri + '-' + ci2"
                          class="range-cell"
                          :class="{ 'has-weight': getRangeCell(slot, ri, ci2).weight > 0, 'clickable': getRangeCell(slot, ri, ci2).weight > 0 }"
                          :style="{ opacity: Math.max(0.15, getRangeCell(slot, ri, ci2).weight) }"
                          :title="getRangeCellTooltip(slot, ri, ci2)"
                          @click="openComboDetail(slot, ri, ci2)"
                        >
                          <span class="range-cell-label">{{ getRangeCellLabel(ri, ci2) }}</span>
                          <span v-if="getRangeCell(slot, ri, ci2).weight > 0" class="range-cell-pct">{{ (getRangeCell(slot, ri, ci2).weight * 100).toFixed(0) }}</span>
                        </div>
                      </template>
                    </div>
                  </div>

                  <!-- Combo input + Pick button -->
                  <div class="combo-pick-row">
                    <span class="field-label-sm">Hand:</span>
                    <input
                      v-model="getSlotForm(slot.id).comboInput"
                      class="combo-input"
                      placeholder="e.g. AsKh"
                      maxlength="4"
                      @keyup.enter="walkAndPick(slot)"
                    />
                    <button
                      class="run-btn"
                      :disabled="getSlotForm(slot.id).running || getSlotForm(slot.id).comboInput.trim().length !== 4"
                      @click="walkAndPick(slot)"
                    >
                      {{ getSlotForm(slot.id).running ? 'Picking...' : 'Pick Hand' }}
                    </button>
                  </div>
                  <div v-if="getSlotForm(slot.id).runError" class="slot-error">{{ getSlotForm(slot.id).runError }}</div>
                </div>
              </template>

              <!-- complete: show picked combo + inline review -->
              <template v-else-if="slot.status === 'complete'">
                <div class="complete-section">
                  <span class="picked-combo">{{ slot.planned_hero_hand }}</span>
                  <span v-if="slot.board" class="picked-board">on {{ slot.board }}</span>
                  <span v-if="getSlotForm(slot.id).puzzleSaved" class="saved-badge">Saved</span>
                  <button class="repick-btn" @click="onRepickSlot(slot)">Repick Hand</button>
                </div>
                <!-- Show action line for reference -->
                <div v-if="slot.line && slot.line.length > 0" class="action-line-display">
                  <span class="action-line-label">Line:</span>
                  <span
                    v-for="(token, idx) in slot.line"
                    :key="idx"
                    class="action-token"
                    :class="{ 'is-decision': idx === slot.decision_idx }"
                  >
                    <span class="action-position-mini">{{ getActingPosition(idx, getConfigData(ci).ip_position, getConfigData(ci).oop_position) }}</span>
                    {{ token }}
                  </span>
                </div>

                <!-- Inline puzzle review -->
                <div v-if="getSlotForm(slot.id).puzzleLoading" class="path-loading" style="margin-top:8px">Loading puzzle data...</div>
                <div v-else-if="getSlotForm(slot.id).puzzleData" class="inline-review">
                  <!-- Solver data table -->
                  <div class="solver-table-section">
                    <div class="review-label">Solver Data</div>
                    <table class="solver-table">
                      <thead><tr><th>Action</th><th>Freq</th><th>EV</th></tr></thead>
                      <tbody>
                        <tr v-for="a in getSlotForm(slot.id).actionSelections" :key="a.action">
                          <td>{{ a.action }}</td>
                          <td>{{ formatFrequency(a.freq) }}</td>
                          <td>{{ formatEV(a.ev) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Per-action cards -->
                  <div class="review-label">Answer Options</div>
                  <div class="review-action-cards">
                    <div
                      v-for="(a, ai) in getSlotForm(slot.id).actionSelections"
                      :key="a.action"
                      class="review-action-card"
                      :class="{ 'is-correct': a.correct }"
                    >
                      <div class="review-action-header">
                        <label class="review-checkbox">
                          <input type="checkbox" v-model="getSlotForm(slot.id).actionSelections[ai].selected" />
                          Include
                        </label>
                        <label class="review-checkbox">
                          <input type="checkbox" v-model="getSlotForm(slot.id).actionSelections[ai].correct" />
                          Correct
                        </label>
                        <span class="review-action-name">{{ a.action }}</span>
                        <span class="review-action-stats">{{ formatFrequency(a.freq) }} | {{ formatEV(a.ev) }}</span>
                      </div>
                      <textarea
                        v-model="getSlotForm(slot.id).actionSelections[ai].explanation"
                        rows="2"
                        class="review-explanation"
                        :placeholder="a.correct ? 'Explain why this is correct...' : 'Optional: explain why this is wrong...'"
                      ></textarea>
                    </div>
                  </div>

                  <!-- Difficulty -->
                  <div class="review-row">
                    <span class="field-label-sm">Difficulty:</span>
                    <select v-model="getSlotForm(slot.id).difficulty" class="select-input-sm">
                      <option :value="1">Easy</option>
                      <option :value="2">Medium</option>
                      <option :value="3">Hard</option>
                    </select>
                  </div>

                  <!-- Save button -->
                  <div class="review-actions">
                    <button
                      class="run-btn"
                      :disabled="getSlotForm(slot.id).puzzleSaving"
                      @click="savePuzzleForSlot(slot)"
                    >
                      {{ getSlotForm(slot.id).puzzleSaving ? 'Saving...' : (getSlotForm(slot.id).puzzleSaved ? 'Update Puzzle' : 'Save Puzzle') }}
                    </button>
                  </div>
                </div>
              </template>
            </div>
          </template>

          <div v-else-if="!cf.locked" class="waiting-hint">
            Select preflop actions and lock to start building spots.
          </div>
        </div>
      </div>

    </template>

    <!-- Import JSON Modal -->
    <div v-if="showImportModal" class="modal-overlay" @click.self="showImportModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h2>Import Day Plan JSON</h2>
          <button class="close-btn" @click="showImportModal = false">&times;</button>
        </div>
        <textarea v-model="importJson" class="import-textarea" placeholder='Paste JSON here...' rows="16"></textarea>
        <div v-if="importError" class="error">{{ importError }}</div>
        <div v-if="importResult" class="import-result">
          <div class="result-success">Created {{ importResult.flop_spots_created }} flop puzzles</div>
          <div v-if="importResult.errors.length > 0" class="result-errors">
            <div v-for="(err, i) in importResult.errors" :key="i" class="result-error">{{ err }}</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="cancel-btn" @click="showImportModal = false">Cancel</button>
          <button class="import-submit-btn" :disabled="importLoading || !importJson.trim()" @click="doImport">
            {{ importLoading ? 'Importing...' : 'Import' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Combo Detail Modal -->
    <div v-if="comboDetailModal.visible" class="modal-overlay" @click.self="closeComboDetail">
      <div class="combo-detail-modal">
        <div class="modal-header">
          <h2>{{ comboDetailModal.handKey }} — Suit Breakdown</h2>
          <button class="close-btn" @click="closeComboDetail">&times;</button>
        </div>
        <div class="combo-list">
          <div v-for="combo in comboDetailModal.combos" :key="combo.combo" class="combo-row">
            <div class="combo-cards">
              <template v-for="(card, idx) in formatComboWithSuits(combo.combo)" :key="idx">
                <span class="card-display" :style="{ color: card.color }">{{ card.rank }}{{ card.symbol }}</span>
              </template>
            </div>
            <div class="combo-weight">{{ (combo.weight * 100).toFixed(0) }}%</div>
            <div class="combo-actions">
              <span
                v-for="(freq, action) in combo.actions"
                :key="action"
                class="action-chip"
              >{{ action }}: {{ (freq * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.day-plan-creator { max-width: 900px; margin: 0 auto; }

.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.back-btn { padding: 8px 12px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; font-size: 13px; cursor: pointer; }
.back-btn:hover { background: #e9ecef; }
.header-content { flex: 1; display: flex; align-items: center; justify-content: space-between; }
.header-content h1 { margin: 0; font-size: 24px; }
.header-actions { display: flex; align-items: center; gap: 12px; }
.progress-badge { padding: 6px 12px; background: #e3f2fd; color: #1976d2; border-radius: 20px; font-size: 13px; font-weight: 600; }
.import-btn { padding: 6px 14px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; font-size: 13px; cursor: pointer; }
.import-btn:hover { background: #e9ecef; }

.loading { color: #666; font-style: italic; padding: 40px; text-align: center; }
.error { background: #ffebee; color: #c62828; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }

/* Config section */
.config-section { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
.config-section-header { display: flex; align-items: center; gap: 12px; cursor: pointer; padding-bottom: 12px; border-bottom: 1px solid #eee; margin-bottom: 16px; }
.config-section-header h2 { margin: 0; font-size: 16px; font-weight: 600; }
.config-desc { font-size: 13px; color: #666; flex: 1; }
.locked-badge { padding: 3px 10px; background: #e8f5e9; color: #2e7d32; border-radius: 12px; font-size: 11px; font-weight: 600; }
.unlock-btn { padding: 3px 10px; background: #fff3e0; border: 1px solid #ffb74d; border-radius: 12px; font-size: 11px; font-weight: 600; color: #e65100; cursor: pointer; }
.unlock-btn:hover:not(:disabled) { background: #ffe0b2; }
.unlock-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.scenario-info { display: flex; flex-direction: column; gap: 2px; margin-bottom: 14px; }
.scenario-desc { font-size: 12px; color: #1976d2; font-weight: 500; }
.scenario-positions { font-size: 11px; color: #666; }
.scenario-positions strong { color: #333; }

.waiting-hint { font-size: 13px; color: #999; font-style: italic; padding: 12px 0; }

/* Preflop builder */
.preflop-builder { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.field-label { font-size: 13px; font-weight: 600; color: #555; white-space: nowrap; }
.preflop-steps { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.path-chip { padding: 4px 10px; background: #e3f2fd; border: 1px solid #90caf9; border-radius: 14px; font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.path-chip:hover { background: #ffcdd2; border-color: #e57373; }
.path-done { font-size: 12px; color: #28a745; font-weight: 600; }
.path-loading { font-size: 12px; color: #999; font-style: italic; }
.preflop-select { padding: 5px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
.reset-link { padding: 4px 8px; background: transparent; border: none; color: #999; font-size: 12px; cursor: pointer; text-decoration: underline; }
.reset-link:hover { color: #c62828; }
.lock-btn { padding: 6px 16px; background: #2e7d32; color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.lock-btn:hover:not(:disabled) { background: #1b5e20; }
.lock-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* Slot panel */
.slot-panel { background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.slot-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.slot-label { font-size: 14px; font-weight: 700; color: #333; }
.slot-hint { font-size: 10px; color: #888; font-style: italic; }
.slot-board { font-size: 12px; font-family: monospace; color: #666; background: #e8e8e8; padding: 2px 8px; border-radius: 4px; }
.slot-status { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; }
.status-empty { background: #f0f0f0; color: #888; }
.status-sim_ready { background: #fff3e0; color: #e65100; }
.status-complete { background: #e8f5e9; color: #2e7d32; }

/* Slot form */
.slot-form { padding-top: 4px; }

/* Card picker */
.card-field { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.field-label-sm { font-size: 12px; font-weight: 600; color: #666; white-space: nowrap; min-width: 50px; }
.selected-cards { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.card-chip { padding: 3px 7px; background: #fff; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; font-weight: 700; font-family: monospace; cursor: pointer; }
.card-chip:hover { border-color: #e57373; background: #ffebee; }
.pick-card-btn { padding: 3px 10px; background: #e3f2fd; border: 1px solid #90caf9; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; color: #1976d2; }
.pick-card-btn:hover { background: #bbdefb; }

.card-grid {
  display: grid; grid-template-columns: repeat(13, 1fr); gap: 2px;
  margin-bottom: 10px; padding: 6px; background: #f0f0f0; border-radius: 6px;
}
.card-cell {
  padding: 4px 2px; font-size: 12px; font-weight: 700; font-family: monospace;
  text-align: center; background: #fff; border: 1px solid #ddd; border-radius: 3px; cursor: pointer; line-height: 1.2;
}
.card-cell:hover:not(.disabled) { background: #e3f2fd; border-color: #1976d2; }
.card-cell.selected { background: #1976d2; color: #fff !important; border-color: #0d47a1; }
.card-cell.disabled { opacity: 0.25; cursor: not-allowed; }

/* Inline fields */
.inline-field { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.select-input-sm { padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }

/* Action line */
.actions-field { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.action-list { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.action-item { display: flex; align-items: center; gap: 6px; }
.action-position {
  font-size: 11px; font-weight: 700; color: #888; min-width: 32px; text-align: center;
  padding: 2px 4px; background: #f0f0f0; border-radius: 3px;
}
.action-position.is-hero { background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }
.action-select { padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 12px; font-family: monospace; min-width: 80px; }
.hero-check { display: flex; align-items: center; gap: 3px; font-size: 11px; color: #555; cursor: pointer; white-space: nowrap; }
.hero-check input { margin: 0; cursor: pointer; }
.hero-check input:disabled { cursor: not-allowed; opacity: 0.4; }
.add-action-btn { padding: 3px 10px; background: transparent; border: 1px dashed #aaa; border-radius: 4px; font-size: 11px; color: #666; cursor: pointer; align-self: flex-start; }
.add-action-btn:hover { background: #e9ecef; border-color: #666; }
.action-terminal { font-size: 11px; color: #28a745; font-style: italic; padding: 2px 0; }
.remove-btn-tiny { width: 18px; height: 18px; padding: 0; border: none; background: transparent; color: #bbb; font-size: 14px; cursor: pointer; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.remove-btn-tiny:hover { background: #ffebee; color: #dc3545; }

/* Slot actions */
.slot-actions { margin-top: 8px; display: flex; align-items: center; gap: 12px; }
.run-btn { padding: 8px 20px; background: #1976d2; color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.run-btn:hover:not(:disabled) { background: #1565c0; }
.run-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.slot-error { font-size: 12px; color: #c62828; }

/* Combo pick */
.combo-pick-row { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.combo-input {
  width: 80px; padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px;
  font-size: 14px; font-weight: 600; font-family: monospace; text-transform: capitalize;
}

/* Node info bar */
.node-info-bar { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: #e8f5e9; border-radius: 6px; margin-bottom: 10px; flex-wrap: wrap; }
.node-position { font-size: 12px; font-weight: 700; color: #2e7d32; }
.node-action-freq { font-size: 12px; color: #333; padding: 2px 8px; background: #fff; border-radius: 4px; border: 1px solid #c8e6c9; }
.node-action-freq strong { color: #1976d2; }

/* Range grid */
.range-grid-section { margin: 12px 0; }
.range-grid-header { font-size: 12px; font-weight: 600; color: #555; margin-bottom: 6px; }
.range-grid-13x13 {
  display: grid; grid-template-columns: repeat(13, 1fr); gap: 1px;
  background: #e0e0e0; border-radius: 4px; overflow: hidden; max-width: 420px;
}
.range-cell {
  background: #fff; padding: 2px; text-align: center; font-size: 9px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 28px; cursor: default; position: relative;
}
.range-cell.has-weight { background: #c8e6c9; }
.range-cell-label { font-weight: 600; color: #333; line-height: 1.1; }
.range-cell-pct { font-size: 8px; color: #666; line-height: 1; }

/* Complete */
.complete-section { display: flex; align-items: center; gap: 10px; }
.picked-combo { font-size: 15px; font-weight: 700; font-family: monospace; color: #2e7d32; }
.picked-board { font-size: 12px; color: #666; }
.saved-badge { padding: 3px 10px; background: #e8f5e9; color: #2e7d32; border-radius: 12px; font-size: 11px; font-weight: 600; }
.repick-btn { padding: 4px 10px; background: #fff3e0; border: 1px solid #ffb74d; border-radius: 4px; font-size: 11px; color: #e65100; cursor: pointer; margin-left: auto; }
.repick-btn:hover { background: #ffe0b2; }
.action-line-display { display: flex; align-items: center; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.action-line-label { font-size: 11px; color: #888; }
.action-token { display: inline-flex; align-items: center; gap: 3px; padding: 2px 8px; background: #f0f0f0; border-radius: 4px; font-size: 11px; font-family: monospace; }
.action-token.is-decision { background: #e8f5e9; border: 1px solid #81c784; color: #2e7d32; font-weight: 600; }
.action-position-mini { font-size: 9px; color: #666; font-weight: 600; }

/* Inline review */
.inline-review { margin-top: 12px; padding-top: 12px; border-top: 1px solid #e0e0e0; }
.review-label { font-size: 10px; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; margin-top: 10px; }
.solver-table-section { margin-bottom: 8px; }
.solver-table { width: 100%; border-collapse: collapse; }
.solver-table th, .solver-table td { padding: 5px 8px; text-align: left; border-bottom: 1px solid #eee; font-size: 12px; }
.solver-table th { font-size: 10px; font-weight: 600; color: #999; text-transform: uppercase; }
.review-action-cards { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.review-action-card { background: #fff; border: 1px solid #dee2e6; border-radius: 6px; padding: 8px 10px; }
.review-action-card.is-correct { background: #d4edda; border-color: #28a745; }
.review-action-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; flex-wrap: wrap; }
.review-checkbox { display: flex; align-items: center; gap: 3px; font-size: 11px; color: #555; cursor: pointer; white-space: nowrap; }
.review-checkbox input { margin: 0; cursor: pointer; }
.review-action-name { font-weight: 600; font-size: 13px; }
.review-action-stats { font-size: 11px; color: #888; margin-left: auto; }
.review-explanation { width: 100%; font-size: 12px; padding: 5px 8px; border: 1px solid #ddd; border-radius: 4px; resize: vertical; box-sizing: border-box; }
.review-action-card.is-correct .review-explanation { border-color: #28a745; }
.review-row { display: flex; align-items: center; gap: 8px; margin: 10px 0; }
.review-actions { margin-top: 10px; display: flex; align-items: center; gap: 10px; }

/* Modal */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-content { background: #fff; border-radius: 12px; padding: 24px; max-width: 640px; width: 90%; max-height: 80vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-header h2 { margin: 0; font-size: 18px; }
.close-btn { background: none; border: none; font-size: 24px; cursor: pointer; color: #666; }
.import-textarea { width: 100%; font-family: monospace; font-size: 12px; padding: 12px; border: 1px solid #dee2e6; border-radius: 6px; resize: vertical; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.cancel-btn { padding: 6px 12px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; font-size: 13px; cursor: pointer; }
.cancel-btn:hover { background: #e9ecef; }
.import-submit-btn { padding: 8px 20px; background: #1976d2; color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.import-submit-btn:hover:not(:disabled) { background: #1565c0; }
.import-submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.import-result { margin-top: 12px; }
.result-success { color: #28a745; font-weight: 600; margin-bottom: 8px; }
.result-errors { background: #fff3cd; border-radius: 6px; padding: 8px 12px; }
.result-error { font-size: 12px; color: #856404; margin-bottom: 4px; }

/* Range grid hint and clickable cells */
.range-grid-hint { font-weight: 400; color: #888; font-size: 10px; }
.range-cell.clickable { cursor: pointer; }
.range-cell.clickable:hover { outline: 2px solid #1976d2; z-index: 1; }

/* Combo detail modal */
.combo-detail-modal {
  background: #fff; border-radius: 12px; padding: 20px; max-width: 500px; width: 90%;
  max-height: 70vh; overflow-y: auto;
}
.combo-list { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.combo-row {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  background: #f8f9fa; border-radius: 8px; border: 1px solid #e0e0e0;
}
.combo-cards { display: flex; gap: 2px; min-width: 60px; }
.card-display { font-size: 18px; font-weight: 700; font-family: monospace; }
.combo-weight {
  font-size: 14px; font-weight: 600; color: #333; min-width: 45px; text-align: right;
  padding: 3px 8px; background: #e8f5e9; border-radius: 4px;
}
.combo-actions { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.action-chip {
  font-size: 11px; padding: 3px 8px; background: #e3f2fd; border: 1px solid #90caf9;
  border-radius: 12px; color: #1565c0; font-weight: 500; white-space: nowrap;
}
</style>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  config: {
    type: Object,
    required: true
  },
  existingSims: {
    type: Array,
    default: () => []
  },
  puzzleMap: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['slot-click', 'link-sim', 'reset-slot', 'pick-combo'])

// Group existing sims by street
const simsByStreet = computed(() => {
  const grouped = { flop: [], turn: [], river: [] }
  for (const sim of props.existingSims) {
    if (grouped[sim.street]) {
      grouped[sim.street].push(sim)
    }
  }
  return grouped
})

// Organize slots into tree structure
// Structure: Flop1 -> Turn1, Flop2 -> Turn2 -> River
const slotTree = computed(() => {
  const slots = props.config.slots

  // Find flops (no parent)
  const flop1 = slots[0] // First flop
  const flop2 = slots[2] // Second flop

  // Find turn1 (parent is flop1)
  const turn1 = slots[1]

  // Find turn2 (parent is flop2)
  const turn2 = slots[3]

  // Find river (parent is turn2)
  const river = slots[4]

  return [
    {
      slot: flop1,
      children: [
        { slot: turn1, children: [] }
      ]
    },
    {
      slot: flop2,
      children: [
        {
          slot: turn2,
          children: [
            { slot: river, children: [] }
          ]
        }
      ]
    }
  ]
})

function getSlotStatusClass(slot) {
  return {
    'slot-empty': slot.status === 'empty',
    'slot-ready': slot.status === 'sim_ready',
    'slot-complete': slot.status === 'complete'
  }
}

function getSlotStatusText(slot) {
  if (slot.status === 'empty') {
    if (slot.planned_hero_hand && slot.street !== 'flop') return 'Waiting'
    return 'Add Board'
  }
  if (slot.status === 'sim_ready') return slot.top_combos ? 'Pick Combo' : 'Fill Puzzle'
  if (slot.status === 'complete') return 'Done'
  return slot.status
}

function isSlotBlocked(slot) {
  if (slot.street === 'flop') return false
  const parent = props.config.slots.find(s => s.id === slot.parent_slot_id)
  return !parent || (parent.status !== 'sim_ready' && parent.status !== 'complete')
}

function formatBoard(board) {
  if (!board) return ''
  // Format: "AhKd2c" -> "Ah Kd 2c"
  return board.match(/.{2}/g)?.join(' ') || board
}

function onSlotClick(slot) {
  if (!isSlotBlocked(slot)) {
    emit('slot-click', slot)
  }
}

function linkExistingSim(slot, sim) {
  emit('link-sim', slot, sim.id)
}

function resetSlot(slot) {
  emit('reset-slot', slot)
}

function onPickCombo(slot, combo) {
  emit('pick-combo', slot, combo)
}

function getPuzzle(slot) {
  if (!slot.puzzle_id) return null
  return props.puzzleMap[slot.puzzle_id] || null
}

// Find existing sims that match a slot's street
function getMatchingSimsForSlot(slot) {
  return simsByStreet.value[slot.street] || []
}
</script>

<template>
  <div class="preflop-config-tree">
    <!-- Existing sims summary -->
    <div v-if="existingSims.length > 0" class="existing-summary">
      <span class="summary-label">Existing sims:</span>
      <span class="summary-count">{{ simsByStreet.flop.length }} flops</span>
      <span v-if="simsByStreet.turn.length" class="summary-count">{{ simsByStreet.turn.length }} turns</span>
      <span v-if="simsByStreet.river.length" class="summary-count">{{ simsByStreet.river.length }} rivers</span>
    </div>

    <div
      v-for="(branch, branchIdx) in slotTree"
      :key="branch.slot.id"
      class="tree-branch"
    >
      <!-- Flop Slot -->
      <div
        class="slot-card"
        :class="[getSlotStatusClass(branch.slot), { blocked: isSlotBlocked(branch.slot) }]"
        @click="onSlotClick(branch.slot)"
      >
        <div class="slot-header">
          <span class="slot-street">FLOP {{ branchIdx + 1 }}</span>
          <span class="slot-status">{{ getSlotStatusText(branch.slot) }}</span>
          <button
            v-if="branch.slot.status !== 'empty'"
            class="remove-btn"
            title="Remove this spot"
            @click.stop="resetSlot(branch.slot)"
          >&times;</button>
        </div>
        <div v-if="branch.slot.board" class="slot-board">
          {{ formatBoard(branch.slot.board) }}
          <span v-if="branch.slot.planned_hero_hand" class="planned-hand">| {{ branch.slot.planned_hero_hand }}</span>
        </div>
        <!-- Top combos picker for sim_ready slots -->
        <div v-if="branch.slot.status === 'sim_ready' && branch.slot.top_combos && branch.slot.top_combos.length > 0" class="top-combos" @click.stop>
          <div class="combos-label">Pick hero hand:</div>
          <div class="combos-list">
            <button
              v-for="(tc, idx) in branch.slot.top_combos.slice(0, 10)"
              :key="idx"
              class="combo-chip"
              @click.stop="onPickCombo(branch.slot, tc.combo)"
              :title="`${tc.action} @ ${(tc.freq * 100).toFixed(0)}%`"
            >
              {{ tc.combo }} <span class="combo-freq">{{ (tc.freq * 100).toFixed(0) }}%</span>
            </button>
          </div>
        </div>
        <div v-if="getPuzzle(branch.slot)" class="slot-puzzle-info">
          <span class="puzzle-hero">Hero: {{ getPuzzle(branch.slot).hero }}</span>
          <span class="puzzle-question">{{ getPuzzle(branch.slot).question_text }}</span>
        </div>
        <!-- Existing sims for empty flop slots -->
        <div v-if="branch.slot.status === 'empty' && getMatchingSimsForSlot(branch.slot).length > 0" class="existing-sims">
          <div class="existing-label">Or use existing ({{ getMatchingSimsForSlot(branch.slot).length }}):</div>
          <div class="existing-chips-scroll">
            <button
              v-for="sim in getMatchingSimsForSlot(branch.slot)"
              :key="sim.id"
              class="sim-chip"
              @click.stop="linkExistingSim(branch.slot, sim)"
              :title="sim.board"
            >
              {{ formatBoard(sim.board) }}
            </button>
          </div>
        </div>
      </div>

      <!-- Turn children -->
      <div class="slot-children">
        <div
          v-for="turnBranch in branch.children"
          :key="turnBranch.slot.id"
          class="turn-branch"
        >
          <div class="tree-connector"></div>
          <div
            class="slot-card turn"
            :class="[getSlotStatusClass(turnBranch.slot), { blocked: isSlotBlocked(turnBranch.slot) }]"
            @click="onSlotClick(turnBranch.slot)"
          >
            <div class="slot-header">
              <span class="slot-street">TURN {{ branchIdx + 1 }}</span>
              <span class="slot-status">{{ isSlotBlocked(turnBranch.slot) ? 'Blocked' : getSlotStatusText(turnBranch.slot) }}</span>
              <button
                v-if="turnBranch.slot.status !== 'empty'"
                class="remove-btn"
                title="Remove this spot"
                @click.stop="resetSlot(turnBranch.slot)"
              >&times;</button>
            </div>
            <div v-if="turnBranch.slot.board" class="slot-board">
              {{ formatBoard(turnBranch.slot.board) }}
            </div>
            <div v-if="turnBranch.slot.planned_hero_hand && turnBranch.slot.status === 'empty'" class="slot-planned">
              {{ formatBoard(turnBranch.slot.board || '') }} + ? | {{ turnBranch.slot.planned_hero_hand }}
            </div>
            <div v-if="getPuzzle(turnBranch.slot)" class="slot-puzzle-info">
              <span class="puzzle-hero">Hero: {{ getPuzzle(turnBranch.slot).hero }}</span>
              <span class="puzzle-question">{{ getPuzzle(turnBranch.slot).question_text }}</span>
            </div>
          </div>

          <!-- River children -->
          <div v-if="turnBranch.children.length > 0" class="slot-children">
            <div
              v-for="riverBranch in turnBranch.children"
              :key="riverBranch.slot.id"
              class="river-branch"
            >
              <div class="tree-connector"></div>
              <div
                class="slot-card river"
                :class="[getSlotStatusClass(riverBranch.slot), { blocked: isSlotBlocked(riverBranch.slot) }]"
                @click="onSlotClick(riverBranch.slot)"
              >
                <div class="slot-header">
                  <span class="slot-street">RIVER</span>
                  <span class="slot-status">{{ isSlotBlocked(riverBranch.slot) ? 'Blocked' : getSlotStatusText(riverBranch.slot) }}</span>
                  <button
                    v-if="riverBranch.slot.status !== 'empty'"
                    class="remove-btn"
                    title="Remove this spot"
                    @click.stop="resetSlot(riverBranch.slot)"
                  >&times;</button>
                </div>
                <div v-if="riverBranch.slot.board" class="slot-board">
                  {{ formatBoard(riverBranch.slot.board) }}
                </div>
                <div v-if="riverBranch.slot.planned_hero_hand && riverBranch.slot.status === 'empty'" class="slot-planned">
                  {{ formatBoard(riverBranch.slot.board || '') }} + ? | {{ riverBranch.slot.planned_hero_hand }}
                </div>
                <div v-if="getPuzzle(riverBranch.slot)" class="slot-puzzle-info">
                  <span class="puzzle-hero">Hero: {{ getPuzzle(riverBranch.slot).hero }}</span>
                  <span class="puzzle-question">{{ getPuzzle(riverBranch.slot).question_text }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.preflop-config-tree {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.existing-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #e8f5e9;
  border-radius: 6px;
  font-size: 12px;
}

.summary-label {
  color: #2e7d32;
  font-weight: 600;
}

.summary-count {
  color: #388e3c;
}

.tree-branch {
  display: flex;
  flex-direction: column;
}

.slot-card {
  padding: 12px 16px;
  border-radius: 8px;
  border: 2px solid #dee2e6;
  background: #f8f9fa;
  cursor: pointer;
  transition: all 0.2s;
}

.slot-card:hover:not(.blocked) {
  border-color: #1976d2;
  background: #e3f2fd;
}

.slot-card.blocked {
  opacity: 0.5;
  cursor: not-allowed;
}

.slot-card.slot-empty {
  border-style: dashed;
}

.slot-card.slot-ready {
  border-color: #ffc107;
  background: #fff8e1;
}

.slot-card.slot-complete {
  border-color: #28a745;
  background: #d4edda;
}

.slot-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.remove-btn {
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: transparent;
  color: #999;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  flex-shrink: 0;
}

.remove-btn:hover {
  background: #ffebee;
  color: #dc3545;
}

.slot-street {
  font-size: 11px;
  font-weight: 700;
  color: #666;
  letter-spacing: 0.5px;
}

.slot-status {
  font-size: 11px;
  font-weight: 600;
  color: #1976d2;
}

.slot-card.slot-ready .slot-status {
  color: #f57c00;
}

.slot-card.slot-complete .slot-status {
  color: #28a745;
}

.slot-card.blocked .slot-status {
  color: #999;
}

.slot-board {
  margin-top: 8px;
  font-family: monospace;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.slot-children {
  margin-left: 24px;
  padding-left: 16px;
  border-left: 2px solid #dee2e6;
}

.turn-branch,
.river-branch {
  position: relative;
  margin-top: 12px;
}

.tree-connector {
  position: absolute;
  left: -18px;
  top: 16px;
  width: 16px;
  height: 2px;
  background: #dee2e6;
}

.slot-card.turn,
.slot-card.river {
  margin-left: 0;
}

/* Existing sims */
.existing-sims {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #dee2e6;
}

.existing-label {
  font-size: 10px;
  color: #666;
  margin-bottom: 6px;
}

.existing-chips-scroll {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  max-height: 120px;
  overflow-y: auto;
  padding-right: 4px;
}

.sim-chip {
  padding: 4px 8px;
  background: #e3f2fd;
  border: 1px solid #90caf9;
  border-radius: 4px;
  font-size: 11px;
  font-family: monospace;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.sim-chip:hover {
  background: #bbdefb;
  border-color: #1976d2;
}

/* Puzzle info on completed slots */
.slot-puzzle-info {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0,0,0,0.08);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.puzzle-hero {
  font-size: 11px;
  font-weight: 600;
  color: #1976d2;
}

.puzzle-question {
  font-size: 11px;
  color: #555;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.slot-planned {
  margin-top: 6px;
  font-size: 12px;
  font-family: monospace;
  color: #7b1fa2;
  font-weight: 500;
}

.planned-hand {
  color: #7b1fa2;
  font-weight: 500;
  margin-left: 6px;
}

/* Top combos picker */
.top-combos {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #ffc107;
}

.combos-label {
  font-size: 10px;
  color: #f57c00;
  font-weight: 600;
  margin-bottom: 6px;
}

.combos-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.combo-chip {
  padding: 3px 8px;
  background: #fff3e0;
  border: 1px solid #ffcc80;
  border-radius: 4px;
  font-size: 11px;
  font-family: monospace;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.combo-chip:hover {
  background: #ffe0b2;
  border-color: #f57c00;
}

.combo-freq {
  color: #e65100;
  font-weight: 600;
  margin-left: 2px;
}
</style>

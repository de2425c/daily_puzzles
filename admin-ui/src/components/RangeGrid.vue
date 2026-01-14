<script setup>
import { computed } from 'vue'

const props = defineProps({
  range: {
    type: Array,
    required: true
  },
  handOrder: {
    type: Array,
    required: true
  },
  board: {
    type: String,
    default: ''
  },
  heroCombo: {
    type: String,
    default: ''
  },
  clickable: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['select-combo'])

// Ranks from high to low (A-2)
const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

// Map rank character to index
const RANK_ORDER = Object.fromEntries(
  ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A'].map((r, i) => [r, i])
)

// Parse board into card set for blocking check
function getBoardCards(board) {
  const cards = new Set()
  for (let i = 0; i < board.length; i += 2) {
    cards.add(board.slice(i, i + 2))
  }
  return cards
}

// Check if combo is blocked by board
function isBlocked(combo, boardCards) {
  const card1 = combo.slice(0, 2)
  const card2 = combo.slice(2, 4)
  return boardCards.has(card1) || boardCards.has(card2)
}

// Get the hand category for a combo (e.g., "AKs", "AKo", "AA")
function getHandCategory(combo) {
  const r1 = combo[0]
  const r2 = combo[2]
  const s1 = combo[1]
  const s2 = combo[3]

  if (r1 === r2) {
    return { ranks: `${r1}${r1}`, type: 'pair' }
  }

  // Ensure higher rank first
  const r1Val = RANK_ORDER[r1]
  const r2Val = RANK_ORDER[r2]
  const highRank = r1Val > r2Val ? r1 : r2
  const lowRank = r1Val > r2Val ? r2 : r1

  if (s1 === s2) {
    return { ranks: `${highRank}${lowRank}`, type: 'suited' }
  } else {
    return { ranks: `${highRank}${lowRank}`, type: 'offsuit' }
  }
}

// Convert 1326 array to 13x13 grid data
const gridData = computed(() => {
  const boardCards = getBoardCards(props.board)
  const heroCategory = props.heroCombo ? getHandCategory(props.heroCombo) : null

  // Initialize grid
  const grid = RANKS.map((r1, row) =>
    RANKS.map((r2, col) => {
      const isPair = row === col
      const isSuited = row < col  // Upper triangle (row < col) = suited

      // Hand label
      const highRank = RANKS[Math.min(row, col)]
      const lowRank = RANKS[Math.max(row, col)]
      let label
      if (isPair) {
        label = `${r1}${r1}`
      } else if (isSuited) {
        label = `${highRank}${lowRank}s`
      } else {
        label = `${highRank}${lowRank}o`
      }

      return {
        label,
        type: isPair ? 'pair' : (isSuited ? 'suited' : 'offsuit'),
        totalCombos: isPair ? 6 : (isSuited ? 4 : 12),
        weightSum: 0,
        activeCount: 0,
        blockedCount: 0,
        isHero: heroCategory && heroCategory.ranks === (isPair ? label : label.slice(0, 2)) &&
                (isPair || (isSuited ? heroCategory.type === 'suited' : heroCategory.type === 'offsuit')),
        combos: []  // Store available combos for clicking
      }
    })
  )

  // Aggregate 1326 combos into grid cells
  props.handOrder.forEach((combo, idx) => {
    const weight = props.range[idx] || 0
    const category = getHandCategory(combo)
    const blocked = isBlocked(combo, boardCards)

    // Find grid cell
    const r1 = combo[0]
    const r2 = combo[2]
    const r1Idx = RANKS.indexOf(r1 > r2 || (RANK_ORDER[r1] > RANK_ORDER[r2]) ? r1 : r2)
    const r2Idx = RANKS.indexOf(r1 > r2 || (RANK_ORDER[r1] > RANK_ORDER[r2]) ? r2 : r1)

    // Determine correct cell (pairs on diagonal, suited upper, offsuit lower)
    let row, col
    if (r1Idx === r2Idx) {
      // Pair - diagonal
      row = r1Idx
      col = r1Idx
    } else if (category.type === 'suited') {
      // Suited - upper triangle (smaller index is row)
      row = Math.min(r1Idx, r2Idx)
      col = Math.max(r1Idx, r2Idx)
    } else {
      // Offsuit - lower triangle (larger index is row)
      row = Math.max(r1Idx, r2Idx)
      col = Math.min(r1Idx, r2Idx)
    }

    const cell = grid[row][col]

    if (blocked) {
      cell.blockedCount++
    } else {
      cell.weightSum += weight
      if (weight > 0) {
        cell.activeCount++
        cell.combos.push(combo)  // Store combo for clicking
      }
    }
  })

  // Calculate display values
  grid.forEach(row => {
    row.forEach(cell => {
      const availableCombos = cell.totalCombos - cell.blockedCount
      if (availableCombos > 0) {
        // Weight is 0-10000, normalize to 0-1
        cell.frequency = cell.weightSum / (availableCombos * 10000)
      } else {
        cell.frequency = 0
      }
    })
  })

  return grid
})

// Handle cell click - select first available combo from cell
function handleCellClick(cell) {
  if (!props.clickable || cell.combos.length === 0) return

  // Pick the first combo with weight > 0
  const combo = cell.combos[0]
  emit('select-combo', combo)
}

// Calculate total stats
const totalStats = computed(() => {
  let total = 0
  let active = 0
  let blocked = 0

  gridData.value.forEach(row => {
    row.forEach(cell => {
      total += cell.totalCombos
      active += cell.weightSum / 10000
      blocked += cell.blockedCount
    })
  })

  return {
    total: Math.round(total),
    active: active.toFixed(1),
    blocked: Math.round(blocked)
  }
})

// Get cell background color based on frequency
function getCellStyle(cell) {
  if (cell.blockedCount === cell.totalCombos) {
    return { backgroundColor: '#e9ecef' }  // All blocked - gray
  }

  const freq = cell.frequency
  if (freq === 0) {
    return { backgroundColor: '#fff' }
  }

  // Green gradient based on frequency
  const intensity = Math.round(freq * 255)
  const r = 255 - Math.round(freq * 127)  // 255 -> 128
  const g = 255 - Math.round(freq * 50)   // 255 -> 205
  const b = 255 - Math.round(freq * 127)  // 255 -> 128

  return {
    backgroundColor: `rgb(${r}, ${g}, ${b})`
  }
}
</script>

<template>
  <div class="range-grid-container">
    <div class="range-stats">
      <span class="stat">{{ totalStats.active }} combos</span>
      <span class="stat-secondary">({{ totalStats.blocked }} blocked)</span>
    </div>

    <div class="range-grid">
      <!-- Header row with column labels -->
      <div class="grid-row header-row">
        <div class="grid-cell corner"></div>
        <div v-for="rank in RANKS" :key="'h-' + rank" class="grid-cell header">
          {{ rank }}
        </div>
      </div>

      <!-- Data rows -->
      <div v-for="(row, rowIdx) in gridData" :key="'r-' + rowIdx" class="grid-row">
        <!-- Row label -->
        <div class="grid-cell header">{{ RANKS[rowIdx] }}</div>

        <!-- Cells -->
        <div
          v-for="(cell, colIdx) in row"
          :key="'c-' + rowIdx + '-' + colIdx"
          class="grid-cell"
          :class="{
            'pair': cell.type === 'pair',
            'suited': cell.type === 'suited',
            'offsuit': cell.type === 'offsuit',
            'hero': cell.isHero,
            'empty': cell.frequency === 0 && cell.blockedCount < cell.totalCombos,
            'blocked': cell.blockedCount === cell.totalCombos,
            'clickable': clickable && cell.combos.length > 0
          }"
          :style="getCellStyle(cell)"
          :title="`${cell.label}: ${(cell.frequency * 100).toFixed(0)}% (${cell.activeCount}/${cell.totalCombos - cell.blockedCount} combos)${clickable && cell.combos.length > 0 ? ' - Click to select' : ''}`"
          @click="handleCellClick(cell)"
        >
          <span class="cell-label">{{ cell.label }}</span>
          <span v-if="cell.frequency > 0" class="cell-freq">{{ Math.round(cell.frequency * 100) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.range-grid-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.range-stats {
  font-size: 12px;
  color: #666;
}

.stat {
  font-weight: 600;
  color: #333;
}

.stat-secondary {
  margin-left: 6px;
  color: #999;
}

.range-grid {
  display: flex;
  flex-direction: column;
  font-family: monospace;
  font-size: 10px;
  user-select: none;
}

.grid-row {
  display: flex;
}

.grid-cell {
  width: 32px;
  height: 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px solid #ddd;
  margin: -0.5px;
  position: relative;
  cursor: default;
}

.grid-cell.header {
  background: #f5f5f5;
  font-weight: 600;
  color: #666;
}

.grid-cell.corner {
  background: transparent;
  border-color: transparent;
}

.grid-cell.pair {
  border-color: #aaa;
}

.grid-cell.hero {
  border: 2px solid #1976d2;
  z-index: 1;
}

.grid-cell.blocked {
  background: #e9ecef !important;
}

.grid-cell.blocked .cell-label {
  color: #bbb;
}

.cell-label {
  font-size: 9px;
  font-weight: 500;
  color: #333;
  line-height: 1;
}

.cell-freq {
  font-size: 8px;
  color: #666;
  line-height: 1;
}

.grid-cell:not(.header):not(.corner):hover {
  border-color: #1976d2;
  z-index: 2;
}

.grid-cell.clickable {
  cursor: pointer;
}

.grid-cell.clickable:hover {
  border-color: #1976d2;
  border-width: 2px;
  box-shadow: 0 0 4px rgba(25, 118, 210, 0.4);
}
</style>

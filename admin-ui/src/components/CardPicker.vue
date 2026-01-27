<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  visible: Boolean,
  currentCombo: String,
  blockedCards: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['select', 'close'])

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
const SUITS = ['s', 'h', 'd', 'c']
const SUIT_SYMBOLS = { s: '♠', h: '♥', d: '♦', c: '♣' }
const SUIT_COLORS = { s: '#000', h: '#e53935', d: '#1976d2', c: '#2e7d32' }

const selectedCards = ref([])

// Parse blocked cards from board string
const blockedSet = computed(() => {
  const set = new Set()
  props.blockedCards.forEach(card => set.add(card))
  return set
})

// All 52 cards organized by suit
const cardsBySuit = computed(() => {
  return SUITS.map(suit => ({
    suit,
    symbol: SUIT_SYMBOLS[suit],
    color: SUIT_COLORS[suit],
    cards: RANKS.map(rank => ({
      rank,
      card: rank + suit,
      blocked: blockedSet.value.has(rank + suit),
      selected: selectedCards.value.includes(rank + suit)
    }))
  }))
})

function toggleCard(card) {
  if (blockedSet.value.has(card)) return

  const idx = selectedCards.value.indexOf(card)
  if (idx >= 0) {
    selectedCards.value.splice(idx, 1)
  } else if (selectedCards.value.length < 2) {
    selectedCards.value.push(card)
  }
}

function confirm() {
  if (selectedCards.value.length === 2) {
    // Sort so higher rank comes first
    const combo = sortCombo(selectedCards.value[0], selectedCards.value[1])
    emit('select', combo)
    selectedCards.value = []
  }
}

function cancel() {
  selectedCards.value = []
  emit('close')
}

function sortCombo(card1, card2) {
  const rankOrder = 'AKQJT98765432'
  const r1 = rankOrder.indexOf(card1[0])
  const r2 = rankOrder.indexOf(card2[0])
  if (r1 <= r2) {
    return card1 + card2
  }
  return card2 + card1
}

// Reset selection when modal opens
function reset() {
  selectedCards.value = []
}

defineExpose({ reset })
</script>

<template>
  <div v-if="visible" class="modal-overlay" @click.self="cancel">
    <div class="card-picker-modal">
      <div class="modal-header">
        <h3>Select Hero's Hand</h3>
        <button class="close-btn" @click="cancel">&times;</button>
      </div>

      <div class="current-selection">
        <span class="label">Selected:</span>
        <span v-if="selectedCards.length === 0" class="placeholder">Click two cards</span>
        <span v-else class="selected-cards">
          <span
            v-for="card in selectedCards"
            :key="card"
            class="selected-card"
            :style="{ color: SUIT_COLORS[card[1]] }"
          >
            {{ card[0] }}{{ SUIT_SYMBOLS[card[1]] }}
          </span>
        </span>
      </div>

      <div class="card-grid">
        <div v-for="suitGroup in cardsBySuit" :key="suitGroup.suit" class="suit-row">
          <div class="suit-label" :style="{ color: suitGroup.color }">
            {{ suitGroup.symbol }}
          </div>
          <div class="suit-cards">
            <button
              v-for="cardInfo in suitGroup.cards"
              :key="cardInfo.card"
              class="card-btn"
              :class="{
                blocked: cardInfo.blocked,
                selected: cardInfo.selected
              }"
              :style="{ color: cardInfo.blocked ? '#ccc' : suitGroup.color }"
              :disabled="cardInfo.blocked"
              @click="toggleCard(cardInfo.card)"
            >
              {{ cardInfo.rank }}
            </button>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" @click="cancel">Cancel</button>
        <button
          class="btn-primary"
          :disabled="selectedCards.length !== 2"
          @click="confirm"
        >
          Select Hand
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.card-picker-modal {
  background: white;
  border-radius: 12px;
  padding: 20px;
  min-width: 400px;
  max-width: 500px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #666;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #333;
}

.current-selection {
  background: #f5f5f5;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.current-selection .label {
  color: #666;
  font-size: 14px;
}

.current-selection .placeholder {
  color: #999;
  font-style: italic;
}

.selected-cards {
  display: flex;
  gap: 8px;
}

.selected-card {
  font-size: 20px;
  font-weight: 600;
}

.card-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}

.suit-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.suit-label {
  width: 24px;
  font-size: 20px;
  text-align: center;
}

.suit-cards {
  display: flex;
  gap: 4px;
  flex: 1;
}

.card-btn {
  width: 32px;
  height: 36px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.card-btn:hover:not(:disabled) {
  background: #f0f0f0;
  transform: translateY(-1px);
}

.card-btn.selected {
  background: #e3f2fd;
  border-color: #1976d2;
  box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.3);
}

.card-btn.blocked {
  background: #f5f5f5;
  color: #ccc !important;
  cursor: not-allowed;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn-secondary {
  padding: 10px 20px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  font-size: 14px;
}

.btn-secondary:hover {
  background: #f5f5f5;
}

.btn-primary {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  background: #1976d2;
  color: white;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:hover:not(:disabled) {
  background: #1565c0;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}
</style>

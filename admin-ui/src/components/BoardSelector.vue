<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['select', 'close'])

const boardInput = ref('')
const mode = ref('manual') // 'manual', 'random'

const isValidBoard = computed(() => {
  const board = boardInput.value.trim()
  if (board.length !== 6) return false
  // Basic validation: 3 cards, each 2 chars
  const cards = board.match(/.{2}/g)
  if (!cards || cards.length !== 3) return false
  // Check each card format
  const validRanks = 'AKQJT98765432'
  const validSuits = 'cdhs'
  for (const card of cards) {
    const rank = card[0].toUpperCase()
    const suit = card[1].toLowerCase()
    if (!validRanks.includes(rank) || !validSuits.includes(suit)) return false
  }
  // Check for duplicates
  const uniqueCards = new Set(cards.map(c => c[0].toUpperCase() + c[1].toLowerCase()))
  return uniqueCards.size === 3
})

function selectRandom() {
  mode.value = 'random'
  emit('select', null) // null = random
}

function selectManual() {
  if (!isValidBoard.value) return
  emit('select', boardInput.value.trim())
}

function formatBoard(input) {
  // Auto-format as user types
  return input.replace(/\s/g, '')
}

function onInput(e) {
  boardInput.value = formatBoard(e.target.value)
}
</script>

<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Select Board</h2>
        <button class="close-btn" @click="$emit('close')" :disabled="loading">&times;</button>
      </div>

      <div class="modal-body">
        <div class="option-group">
          <button
            class="option-btn"
            :class="{ active: mode === 'random' }"
            @click="mode = 'random'"
            :disabled="loading"
          >
            Random Flop
          </button>
          <button
            class="option-btn"
            :class="{ active: mode === 'manual' }"
            @click="mode = 'manual'"
            :disabled="loading"
          >
            Enter Manually
          </button>
        </div>

        <div v-if="mode === 'manual'" class="manual-input">
          <label>Enter 3 cards (e.g., AhKd2c)</label>
          <input
            type="text"
            :value="boardInput"
            @input="onInput"
            placeholder="AhKd2c"
            maxlength="6"
            :disabled="loading"
          />
          <div v-if="boardInput && !isValidBoard" class="validation-error">
            Enter 3 valid cards (e.g., AhKd2c)
          </div>
        </div>

        <div v-if="mode === 'random'" class="random-info">
          <p>A random flop will be dealt for this sim.</p>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" @click="$emit('close')" :disabled="loading">
          Cancel
        </button>
        <button
          v-if="mode === 'random'"
          class="btn-primary"
          @click="selectRandom"
          :disabled="loading"
        >
          {{ loading ? 'Creating Sim...' : 'Deal Random Flop' }}
        </button>
        <button
          v-else
          class="btn-primary"
          @click="selectManual"
          :disabled="!isValidBoard || loading"
        >
          {{ loading ? 'Creating Sim...' : 'Use This Board' }}
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

.modal-content {
  background: white;
  border-radius: 12px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #999;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover:not(:disabled) {
  color: #333;
}

.modal-body {
  padding: 20px;
}

.option-group {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.option-btn {
  flex: 1;
  padding: 12px;
  border: 2px solid #dee2e6;
  background: #fff;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.option-btn:hover:not(:disabled) {
  border-color: #1976d2;
}

.option-btn.active {
  border-color: #1976d2;
  background: #e3f2fd;
  color: #1976d2;
}

.option-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.manual-input {
  margin-top: 16px;
}

.manual-input label {
  display: block;
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.manual-input input {
  width: 100%;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 18px;
  font-family: monospace;
  text-transform: uppercase;
  letter-spacing: 2px;
}

.manual-input input:focus {
  outline: none;
  border-color: #1976d2;
}

.validation-error {
  color: #c62828;
  font-size: 12px;
  margin-top: 8px;
}

.random-info {
  text-align: center;
  color: #666;
  padding: 20px;
}

.random-info p {
  margin: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
}

.btn-primary,
.btn-secondary {
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #1976d2;
  color: white;
  border: none;
}

.btn-primary:hover:not(:disabled) {
  background: #1565c0;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  color: #666;
  border: 1px solid #ddd;
}

.btn-secondary:hover:not(:disabled) {
  background: #f5f5f5;
}
</style>

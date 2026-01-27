<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  slot: {
    type: Object,
    required: true
  },
  dayPlanId: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['complete', 'close', 'go-to-review'])

function formatBoard(board) {
  if (!board) return ''
  return board.match(/.{2}/g)?.join(' ') || board
}

function getStreetLabel(street) {
  return street.charAt(0).toUpperCase() + street.slice(1)
}
</script>

<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h2>{{ getStreetLabel(slot.street) }} Slot - Ready for Puzzle</h2>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <div class="slot-info">
          <div class="info-row">
            <span class="label">Street</span>
            <span class="value">{{ getStreetLabel(slot.street) }}</span>
          </div>
          <div class="info-row">
            <span class="label">Board</span>
            <span class="value board">{{ formatBoard(slot.board) }}</span>
          </div>
          <div v-if="slot.action_path" class="info-row">
            <span class="label">Action Path</span>
            <span class="value path">{{ slot.action_path }}</span>
          </div>
        </div>

        <div class="instructions">
          <p>This slot has a sim ready. Click below to browse the tree, select a hand, and create a puzzle.</p>
          <p>After approving a puzzle in SpotReview, return here to mark this slot complete.</p>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" @click="$emit('close')">
          Close
        </button>
        <button class="btn-primary" @click="$emit('go-to-review')">
          Browse Tree & Create Puzzle
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
  max-width: 450px;
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

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 20px;
}

.slot-info {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.info-row:not(:last-child) {
  border-bottom: 1px solid #eee;
}

.info-row .label {
  font-size: 13px;
  color: #666;
}

.info-row .value {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.info-row .value.board {
  font-family: monospace;
  font-size: 16px;
}

.info-row .value.path {
  font-family: monospace;
  font-size: 12px;
  color: #666;
}

.instructions {
  color: #666;
  font-size: 14px;
  line-height: 1.5;
}

.instructions p {
  margin: 0 0 8px 0;
}

.instructions p:last-child {
  margin-bottom: 0;
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

.btn-primary:hover {
  background: #1565c0;
}

.btn-secondary {
  background: #fff;
  color: #666;
  border: 1px solid #ddd;
}

.btn-secondary:hover {
  background: #f5f5f5;
}
</style>

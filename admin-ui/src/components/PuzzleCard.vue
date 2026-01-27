<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  puzzle: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['edit'])

const showExplanations = ref(false)

// Extract board from action data
const board = computed(() => {
  const action = props.puzzle.action || {}
  if (action.river?.Cards) return action.river.Cards
  if (action.turn?.Cards) return `${action.flop?.Cards || ''} ${action.turn.Cards}`.trim()
  if (action.flop?.Cards) return action.flop.Cards
  return ''
})

// Get street from data
const street = computed(() => {
  const action = props.puzzle.action || {}
  if (action.river) return 'River'
  if (action.turn) return 'Turn'
  if (action.flop) return 'Flop'
  return 'Preflop'
})

const difficultyLabel = computed(() => {
  const d = props.puzzle.difficulty
  if (d === 1) return 'Easy'
  if (d === 2) return 'Medium'
  return 'Hard'
})

function isCorrect(option) {
  return props.puzzle.correct_answers?.includes(option)
}

function getEv(option) {
  return props.puzzle.ev_by_action?.[option]
}

function getFreq(option) {
  const freq = props.puzzle.action_frequencies?.[option]
  if (freq !== undefined) {
    return `${(freq * 100).toFixed(0)}%`
  }
  return null
}
</script>

<template>
  <div class="puzzle-card">
    <div class="card-header">
      <div class="question-text">{{ puzzle.question_text }}</div>
      <button class="edit-btn" @click="emit('edit', puzzle)">Edit</button>
    </div>

    <div class="card-info">
      <span class="info-item"><strong>Hero:</strong> {{ puzzle.hero }}</span>
      <span class="info-item"><strong>Board:</strong> {{ board || 'N/A' }}</span>
      <span class="info-item"><strong>Street:</strong> {{ street }}</span>
      <span class="info-item"><strong>Pot:</strong> {{ puzzle.pot_size_at_decision }}bb</span>
      <span class="info-item difficulty" :class="`diff-${puzzle.difficulty}`">
        {{ difficultyLabel }}
      </span>
    </div>

    <div class="answer-section">
      <div class="section-label">Answer Options:</div>
      <div class="answers">
        <div
          v-for="option in puzzle.answer_options"
          :key="option"
          class="answer-option"
          :class="{ correct: isCorrect(option) }"
        >
          <span class="answer-marker">{{ isCorrect(option) ? '●' : '○' }}</span>
          <span class="answer-text">{{ option }}</span>
          <span v-if="isCorrect(option)" class="correct-label">Correct</span>
          <span v-if="getEv(option) !== undefined" class="ev-value">
            (EV: {{ getEv(option).toFixed(2) }}bb)
          </span>
          <span v-if="getFreq(option)" class="freq-value">
            {{ getFreq(option) }}
          </span>
        </div>
      </div>
    </div>

    <div class="explanations-section">
      <button class="toggle-btn" @click="showExplanations = !showExplanations">
        {{ showExplanations ? '▼' : '▶' }} Explanations
      </button>
      <div v-if="showExplanations" class="explanations">
        <div
          v-for="(text, action) in puzzle.explanations"
          :key="action"
          class="explanation-item"
        >
          <strong>{{ action }}:</strong> {{ text }}
        </div>
      </div>
    </div>

    <div class="tags-section">
      <span v-for="tag in puzzle.tags" :key="tag" class="tag">{{ tag }}</span>
    </div>
  </div>
</template>

<style scoped>
.puzzle-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.question-text {
  font-size: 15px;
  font-weight: 500;
  color: #333;
  flex: 1;
  padding-right: 12px;
}

.edit-btn {
  background: #1976d2;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.edit-btn:hover {
  background: #1565c0;
}

.card-info {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px;
  background: #f5f5f5;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
}

.info-item {
  color: #666;
}

.info-item strong {
  color: #333;
}

.difficulty {
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 12px;
}

.diff-1 {
  background: #d4edda;
  color: #155724;
}

.diff-2 {
  background: #fff3cd;
  color: #856404;
}

.diff-3 {
  background: #f8d7da;
  color: #721c24;
}

.answer-section {
  margin-bottom: 12px;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.answers {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.answer-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 4px;
  font-size: 14px;
}

.answer-option.correct {
  background: #e8f5e9;
  border: 1px solid #4caf50;
}

.answer-marker {
  color: #999;
}

.answer-option.correct .answer-marker {
  color: #4caf50;
}

.answer-text {
  flex: 1;
}

.correct-label {
  color: #4caf50;
  font-weight: 600;
  font-size: 12px;
}

.ev-value {
  color: #666;
  font-size: 12px;
}

.freq-value {
  color: #1976d2;
  font-size: 12px;
  font-weight: 500;
}

.explanations-section {
  margin-bottom: 12px;
}

.toggle-btn {
  background: none;
  border: none;
  color: #1976d2;
  cursor: pointer;
  font-size: 13px;
  padding: 4px 0;
}

.toggle-btn:hover {
  text-decoration: underline;
}

.explanations {
  margin-top: 8px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}

.explanation-item {
  font-size: 13px;
  color: #444;
  margin-bottom: 8px;
  line-height: 1.5;
}

.explanation-item:last-child {
  margin-bottom: 0;
}

.tags-section {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  font-size: 11px;
  padding: 3px 8px;
  background: #e3f2fd;
  color: #1565c0;
  border-radius: 4px;
}
</style>

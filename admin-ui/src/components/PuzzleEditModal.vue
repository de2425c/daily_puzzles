<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  puzzle: {
    type: Object,
    default: null
  },
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'save'])

// Form state
const questionText = ref('')
const answerOptions = ref([])
const correctAnswers = ref([])
const explanations = ref({})
const difficulty = ref(1)
const tags = ref([])
const scheduledDate = ref('')
const newTag = ref('')

// Watch for puzzle changes and reset form
watch(() => props.puzzle, (puzzle) => {
  if (puzzle) {
    questionText.value = puzzle.question_text || ''
    answerOptions.value = [...(puzzle.answer_options || [])]
    correctAnswers.value = [...(puzzle.correct_answers || [])]
    explanations.value = { ...(puzzle.explanations || {}) }
    difficulty.value = puzzle.difficulty || 1
    tags.value = [...(puzzle.tags || [])]
    scheduledDate.value = puzzle.scheduled_date || ''
  }
}, { immediate: true })

function toggleCorrectAnswer(option) {
  if (correctAnswers.value.includes(option)) {
    correctAnswers.value = correctAnswers.value.filter(a => a !== option)
  } else {
    correctAnswers.value.push(option)
  }
}

function addTag() {
  const tag = newTag.value.trim().toLowerCase()
  if (tag && !tags.value.includes(tag)) {
    tags.value.push(tag)
    newTag.value = ''
  }
}

function removeTag(tag) {
  tags.value = tags.value.filter(t => t !== tag)
}

function save() {
  emit('save', {
    question_text: questionText.value,
    answer_options: answerOptions.value,
    correct_answers: correctAnswers.value,
    explanations: explanations.value,
    difficulty: difficulty.value,
    tags: tags.value,
    scheduled_date: scheduledDate.value
  })
}

function close() {
  emit('close')
}
</script>

<template>
  <div v-if="visible" class="modal-overlay" @click.self="close">
    <div class="modal">
      <div class="modal-header">
        <h2>Edit Puzzle</h2>
        <button class="close-btn" @click="close">&times;</button>
      </div>

      <div class="modal-body">
        <div class="form-group">
          <label>Question Text</label>
          <textarea v-model="questionText" rows="3"></textarea>
        </div>

        <div class="form-group">
          <label>Scheduled Date</label>
          <input type="date" v-model="scheduledDate" />
        </div>

        <div class="form-group">
          <label>Answer Options & Correct Answers</label>
          <div class="answer-list">
            <div
              v-for="option in answerOptions"
              :key="option"
              class="answer-item"
              :class="{ selected: correctAnswers.includes(option) }"
              @click="toggleCorrectAnswer(option)"
            >
              <span class="checkbox">{{ correctAnswers.includes(option) ? '☑' : '☐' }}</span>
              <span>{{ option }}</span>
            </div>
          </div>
          <p class="hint">Click to toggle correct answers (can select multiple)</p>
        </div>

        <div class="form-group">
          <label>Explanations</label>
          <div v-for="option in answerOptions" :key="option" class="explanation-field">
            <label class="sub-label">{{ option }}:</label>
            <textarea
              v-model="explanations[option]"
              rows="2"
              :placeholder="`Explanation for ${option}...`"
            ></textarea>
          </div>
        </div>

        <div class="form-group">
          <label>Difficulty</label>
          <select v-model="difficulty">
            <option :value="1">Easy (1)</option>
            <option :value="2">Medium (2)</option>
            <option :value="3">Hard (3)</option>
          </select>
        </div>

        <div class="form-group">
          <label>Tags</label>
          <div class="tags-display">
            <span v-for="tag in tags" :key="tag" class="tag">
              {{ tag }}
              <button @click="removeTag(tag)" class="tag-remove">&times;</button>
            </span>
          </div>
          <div class="tag-input-row">
            <input
              v-model="newTag"
              placeholder="Add tag..."
              @keydown.enter.prevent="addTag"
            />
            <button @click="addTag" class="add-tag-btn">Add</button>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-cancel" @click="close">Cancel</button>
        <button class="btn-save" @click="save">Save Changes</button>
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

.modal {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
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
  cursor: pointer;
  color: #666;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  color: #333;
}

.sub-label {
  font-weight: 500 !important;
  font-size: 13px !important;
  color: #666 !important;
}

.form-group input[type="text"],
.form-group input[type="date"],
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-group textarea {
  resize: vertical;
}

.answer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.answer-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #f5f5f5;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.answer-item:hover {
  background: #e8e8e8;
}

.answer-item.selected {
  background: #e8f5e9;
  border: 1px solid #4caf50;
}

.checkbox {
  font-size: 16px;
}

.hint {
  font-size: 12px;
  color: #888;
  margin-top: 8px;
}

.explanation-field {
  margin-bottom: 12px;
}

.explanation-field textarea {
  margin-top: 4px;
}

.tags-display {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 4px 8px;
  background: #e3f2fd;
  color: #1565c0;
  border-radius: 4px;
}

.tag-remove {
  background: none;
  border: none;
  color: #1565c0;
  cursor: pointer;
  padding: 0;
  font-size: 14px;
  line-height: 1;
}

.tag-remove:hover {
  color: #d32f2f;
}

.tag-input-row {
  display: flex;
  gap: 8px;
}

.tag-input-row input {
  flex: 1;
}

.add-tag-btn {
  padding: 10px 16px;
  background: #e0e0e0;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.add-tag-btn:hover {
  background: #d0d0d0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
}

.btn-cancel {
  padding: 10px 20px;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-cancel:hover {
  background: #e8e8e8;
}

.btn-save {
  padding: 10px 20px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-save:hover {
  background: #1565c0;
}
</style>

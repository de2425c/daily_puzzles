<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import PuzzleCard from '../components/PuzzleCard.vue'
import PuzzleEditModal from '../components/PuzzleEditModal.vue'

const router = useRouter()
const loading = ref(true)
const error = ref(null)
const workflowStatus = ref({ dates: [] })
const dayPlans = ref({}) // Cache of day plans by date

// Selected date and its puzzles
const selectedDate = ref(null)
const selectedPuzzles = ref([])
const loadingPuzzles = ref(false)

// Edit modal state
const editModalVisible = ref(false)
const editingPuzzle = ref(null)
const saving = ref(false)

onMounted(async () => {
  try {
    workflowStatus.value = await api.getWorkflowStatus(14)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function formatDate(dateStr) {
  const date = new Date(dateStr + 'T00:00:00')
  const options = { weekday: 'short', month: 'short', day: 'numeric' }
  return date.toLocaleDateString('en-US', options)
}

function formatFullDate(dateStr) {
  const date = new Date(dateStr + 'T00:00:00')
  const options = { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }
  return date.toLocaleDateString('en-US', options)
}

function getStatusClass(count, target) {
  if (count >= target) return 'complete'
  if (count > 0) return 'partial'
  return 'empty'
}

async function selectDate(dateStr) {
  if (selectedDate.value === dateStr) {
    // Toggle off if clicking same date
    selectedDate.value = null
    selectedPuzzles.value = []
    return
  }

  selectedDate.value = dateStr
  loadingPuzzles.value = true

  try {
    selectedPuzzles.value = await api.getPuzzlesForDate(dateStr)
  } catch (e) {
    error.value = e.message
    selectedPuzzles.value = []
  } finally {
    loadingPuzzles.value = false
  }
}

function startDayPlan(dateStr) {
  router.push(`/day-plan/${dateStr}`)
}

// Check if a date has a day plan in progress
function hasDayPlan(dateStr) {
  return dayPlans.value[dateStr] && dayPlans.value[dateStr].status !== 'draft'
}

// Get day plan status for a date
function getDayPlanStatus(dateStr) {
  return dayPlans.value[dateStr]?.status || null
}

function openEdit(puzzle) {
  editingPuzzle.value = puzzle
  editModalVisible.value = true
}

function closeEdit() {
  editModalVisible.value = false
  editingPuzzle.value = null
}

async function savePuzzle(data) {
  if (!editingPuzzle.value) return

  saving.value = true
  try {
    const updated = await api.updatePuzzle(editingPuzzle.value.id, data)
    // Update the puzzle in the list
    const index = selectedPuzzles.value.findIndex(p => p.id === editingPuzzle.value.id)
    if (index !== -1) {
      selectedPuzzles.value[index] = updated
    }
    closeEdit()
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function viewInSolver(puzzle) {
  // Navigate to the puzzle review/edit page
  router.push({
    path: `/puzzles/${puzzle.id}/edit`,
    query: { date: puzzle.scheduled_date }
  })
}

async function deletePuzzle(puzzle) {
  if (!confirm(`Delete this puzzle?\n\n"${puzzle.question_text}"`)) {
    return
  }

  try {
    await api.deletePuzzle(puzzle.id)
    // Remove from list
    selectedPuzzles.value = selectedPuzzles.value.filter(p => p.id !== puzzle.id)
    // Update the count in workflowStatus
    const dateItem = workflowStatus.value.dates.find(d => d.date === selectedDate.value)
    if (dateItem) {
      dateItem.count = Math.max(0, dateItem.count - 1)
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}
</script>

<template>
  <div class="home">
    <h1>Puzzle Workflow</h1>

    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else>
      <div class="workflow-section">
        <h2>Daily Puzzle Schedule</h2>
        <p class="subtitle">Click a day to view scheduled puzzles</p>

        <div class="date-grid">
          <div
            v-for="item in workflowStatus.dates"
            :key="item.date"
            class="date-card"
            :class="[getStatusClass(item.count, item.target), { selected: selectedDate === item.date }]"
            @click="selectDate(item.date)"
          >
            <div class="date-label">{{ formatDate(item.date) }}</div>
            <div class="count-display">
              <span class="count">{{ item.count }}</span>
              <span class="separator">/</span>
              <span class="target">{{ item.target }}</span>
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: `${Math.min(100, (item.count / item.target) * 100)}%` }"
              ></div>
            </div>
          </div>
        </div>

        <!-- Selected Date Puzzles -->
        <div v-if="selectedDate" class="puzzles-panel">
          <div class="panel-header">
            <h3>{{ formatFullDate(selectedDate) }}</h3>
            <button
              v-if="selectedPuzzles.length < 10"
              class="start-plan-btn"
              @click="startDayPlan(selectedDate)"
            >
              {{ selectedPuzzles.length === 0 ? 'Start Day Plan' : 'Continue Day Plan' }}
            </button>
          </div>

          <div v-if="loadingPuzzles" class="loading">Loading puzzles...</div>
          <div v-else-if="selectedPuzzles.length === 0" class="empty-puzzles">
            <p>No puzzles scheduled for this day yet.</p>
            <p class="empty-hint">Click "Start Day Plan" to create 10 puzzles for this day.</p>
          </div>
          <div v-else class="puzzle-list">
            <PuzzleCard
              v-for="puzzle in selectedPuzzles"
              :key="puzzle.id"
              :puzzle="puzzle"
              @edit="openEdit"
              @view-solver="viewInSolver"
              @delete="deletePuzzle"
            />
          </div>
        </div>
      </div>

      <!-- Edit Modal -->
      <PuzzleEditModal
        :visible="editModalVisible"
        :puzzle="editingPuzzle"
        @close="closeEdit"
        @save="savePuzzle"
      />

    </template>
  </div>
</template>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
}

h1 {
  font-size: 24px;
  margin-bottom: 24px;
}

h2 {
  font-size: 18px;
  margin: 0 0 8px 0;
}

.subtitle {
  color: #666;
  font-size: 14px;
  margin: 0 0 16px 0;
}

.workflow-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  margin-bottom: 24px;
}

.date-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 12px;
}

.date-card {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 12px;
  text-align: center;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.date-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

.date-card.selected {
  border-color: #1976d2 !important;
  box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.2);
}

.date-card.complete {
  background: #d4edda;
  border-color: #28a745;
}

.date-card.partial {
  background: #fff3cd;
  border-color: #ffc107;
}

.date-card.empty {
  background: #f8f9fa;
  border-color: #dee2e6;
}

.date-label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.count-display {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 8px;
}

.count {
  color: #333;
}

.separator {
  color: #999;
  margin: 0 2px;
}

.target {
  color: #999;
}

.progress-bar {
  height: 4px;
  background: #e9ecef;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #28a745;
  transition: width 0.3s ease;
}

.date-card.partial .progress-fill {
  background: #ffc107;
}

.date-card.empty .progress-fill {
  background: #dee2e6;
}

/* Puzzles Panel */
.puzzles-panel {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #eee;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.puzzles-panel h3 {
  margin: 0;
  font-size: 16px;
  color: #333;
}

.start-plan-btn {
  padding: 8px 16px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.start-plan-btn:hover {
  background: #1565c0;
}

.empty-puzzles {
  color: #666;
  font-size: 14px;
  padding: 20px;
  text-align: center;
  background: #f8f9fa;
  border-radius: 8px;
}

.empty-puzzles p {
  margin: 0 0 8px 0;
}

.empty-hint {
  font-size: 12px;
  color: #999;
}

.puzzle-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.puzzle-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 6px;
}

.puzzle-title {
  font-weight: 500;
  font-size: 14px;
}

.puzzle-meta {
  display: flex;
  gap: 6px;
}

.tag {
  font-size: 11px;
  padding: 3px 8px;
  background: #e9ecef;
  border-radius: 4px;
  color: #666;
}

.tag.difficulty {
  font-weight: 600;
}

.tag.diff-1 {
  background: #d4edda;
  color: #155724;
}

.tag.diff-2 {
  background: #fff3cd;
  color: #856404;
}

.tag.diff-3 {
  background: #f8d7da;
  color: #721c24;
}

/* Responsive */
@media (max-width: 900px) {
  .date-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 600px) {
  .date-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .action-cards {
    grid-template-columns: 1fr;
  }
  .puzzle-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>

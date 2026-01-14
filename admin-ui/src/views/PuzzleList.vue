<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const puzzles = ref([])
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  try {
    puzzles.value = await api.getPuzzles()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="puzzle-list">
    <h2>Approved Puzzles</h2>
    <p class="subtitle">{{ puzzles.length }} puzzles in the database</p>

    <div v-if="loading" class="loading">Loading puzzles...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="puzzles.length === 0" class="empty">
      No puzzles yet. Review some spots to create puzzles!
    </div>
    <div v-else>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Hero</th>
            <th>Correct</th>
            <th>Difficulty</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="puzzle in puzzles" :key="puzzle.puzzle_id">
            <td>#{{ puzzle.puzzle_id }}</td>
            <td>{{ puzzle.title }}</td>
            <td>{{ puzzle.hero }}</td>
            <td>{{ puzzle.correct_answer }}</td>
            <td>
              <span :class="['difficulty', `d${puzzle.difficulty}`]">
                {{ ['', 'Easy', 'Medium', 'Hard'][puzzle.difficulty] }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.subtitle {
  color: #666;
  margin-top: -10px;
  margin-bottom: 20px;
}

.empty {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

table {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.difficulty {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.d1 { background: #d4edda; color: #155724; }
.d2 { background: #fff3cd; color: #856404; }
.d3 { background: #f8d7da; color: #721c24; }
</style>

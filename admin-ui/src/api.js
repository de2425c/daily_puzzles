import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 180000, // 3 min for solver
})

export default {
  // Hand order for range grid display
  _handOrderCache: null,
  async getHandOrder() {
    if (this._handOrderCache) {
      return this._handOrderCache
    }
    const response = await api.get('/hand-order')
    this._handOrderCache = response.data.hands
    return this._handOrderCache
  },

  // Workflow
  async getWorkflowStatus(days = 14) {
    const response = await api.get('/workflow/status', { params: { days } })
    return response.data
  },

  async getPuzzlesForDate(date) {
    const response = await api.get(`/workflow/puzzles/${date}`)
    return response.data
  },

  async getPuzzleById(puzzleId) {
    const response = await api.get(`/workflow/puzzles/by-id/${puzzleId}`)
    return response.data
  },

  async updatePuzzle(puzzleId, data) {
    const response = await api.put(`/workflow/puzzles/${puzzleId}`, data)
    return response.data
  },

  async getPuzzleTreeData(puzzleId) {
    const response = await api.get(`/workflow/puzzles/${puzzleId}/tree`)
    return response.data
  },

  async deletePuzzle(puzzleId) {
    const response = await api.delete(`/workflow/puzzles/${puzzleId}`)
    return response.data
  },

  // Preflop
  async getPreflopPositions() {
    const response = await api.get('/preflop/positions')
    return response.data
  },

  async getPreflopChildren(path) {
    const pathStr = Array.isArray(path) ? path.join(',') : path
    const response = await api.get('/preflop/children', { params: { path: pathStr } })
    return response.data
  },

  async getPreflopScenario(path) {
    const pathStr = Array.isArray(path) ? path.join(',') : path
    const response = await api.get('/preflop/scenario', { params: { path: pathStr } })
    return response.data
  },

  // Day Plans
  async createDayPlan(scheduledDate) {
    const response = await api.post('/day-plans', {
      scheduled_date: scheduledDate,
    })
    return response.data
  },

  async getDayPlan(date) {
    const response = await api.get(`/day-plans/${date}`)
    return response.data
  },

  async setPreflopConfig(planId, configIdx, preflopPath) {
    const response = await api.put(`/day-plans/${planId}/configs/${configIdx}`, {
      preflop_path: preflopPath,
    })
    return response.data
  },

  async deletePreflopConfig(planId, configIdx) {
    const response = await api.delete(`/day-plans/${planId}/configs/${configIdx}`)
    return response.data
  },

  async importDayPlan(jsonData) {
    const response = await api.post('/day-plans/import', jsonData)
    return response.data
  },

  async createSlotSim(planId, slotId, { board }) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/create-sim`, {
      board,
    })
    return response.data
  },

  async createChildSlotSim(planId, slotId, { actionPath, card }) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/create-child-sim`, {
      action_path: actionPath, card,
    })
    return response.data
  },

  async getNodeInfo(planId, slotId, line = []) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/node-info`, { line })
    return response.data
  },

  async walkLine(planId, slotId, { line, decisionIdx }) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/walk-line`, {
      line, decision_idx: decisionIdx,
    })
    return response.data
  },

  async pickCombo(planId, slotId, combo) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/pick-combo`, {
      combo,
    })
    return response.data
  },

  async resetSlot(planId, slotId) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/reset`)
    return response.data
  },

  async repickSlot(planId, slotId) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/repick`)
    return response.data
  },
}

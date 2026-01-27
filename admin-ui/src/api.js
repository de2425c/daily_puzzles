import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 180000, // 3 min for solver
})

export default {
  // Spots
  async getSpots(status = 'pending', limit = 50) {
    const response = await api.get('/spots', { params: { status, limit } })
    return response.data
  },

  async getSpot(id) {
    const response = await api.get(`/spots/${id}`)
    return response.data
  },

  async approveSpot(id, data) {
    const response = await api.post(`/spots/${id}/approve`, data)
    return response.data
  },

  async rejectSpot(id) {
    const response = await api.post(`/spots/${id}/reject`)
    return response.data
  },

  // Puzzles
  async getPuzzles() {
    const response = await api.get('/puzzles')
    return response.data
  },

  async getPuzzle(id) {
    const response = await api.get(`/puzzles/${id}`)
    return response.data
  },

  // Generate
  async generate(board, scenario, iterations = 500) {
    const response = await api.post('/generate', { board, scenario, iterations })
    return response.data
  },

  // Sims
  async getSims() {
    const response = await api.get('/sims')
    return response.data
  },

  async getSim(id) {
    const response = await api.get(`/sims/${id}`)
    return response.data
  },

  async generateRandomSpot(simId, options = {}) {
    const response = await api.post(`/sims/${simId}/random-spot`, {
      hero_position: options.heroPosition || null,
      hero_combo: options.heroCombo || null,
    })
    return response.data
  },

  async createSpotAtPath(simId, path, combo) {
    const response = await api.post(`/sims/${simId}/create-spot`, {
      path,
      combo,
    })
    return response.data
  },

  // Turn Builder
  async getTreeActions(simId, path = 'r:0') {
    const response = await api.get(`/sims/${simId}/tree/actions`, { params: { path } })
    return response.data
  },

  async getTreeRanges(simId, path) {
    const response = await api.get(`/sims/${simId}/tree/ranges`, { params: { path } })
    return response.data
  },

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

  async createTurnSim(simId, flopActionPath, turnCard = null, iterations = 500) {
    const response = await api.post(`/sims/${simId}/create-turn-sim`, {
      flop_action_path: flopActionPath,
      turn_card: turnCard,
      iterations,
    })
    return response.data
  },

  async createRiverSim(simId, turnActionPath, riverCard = null, iterations = 500) {
    const response = await api.post(`/sims/${simId}/create-river-sim`, {
      turn_action_path: turnActionPath,
      river_card: riverCard,
      iterations,
    })
    return response.data
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

  async updatePuzzle(puzzleId, data) {
    const response = await api.put(`/workflow/puzzles/${puzzleId}`, data)
    return response.data
  },

  // Preflop Builder
  async getPreflopPositions() {
    const response = await api.get('/preflop/positions')
    return response.data
  },

  async getPreflopRfiNode(position) {
    const response = await api.get(`/preflop/${position}/rfi`)
    return response.data
  },

  async getPreflopNode(path) {
    const pathStr = Array.isArray(path) ? path.join(',') : path
    const response = await api.get('/preflop/node', { params: { path: pathStr } })
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

  async createPreflopSim(path, board = null, iterations = 500) {
    const response = await api.post('/preflop/create-sim', {
      path,
      board,
      iterations,
    })
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

  async createSlotSim(planId, slotId, board = null, iterations = 500) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/create-sim`, {
      board,
      iterations,
    })
    return response.data
  },

  async createChildSlotSim(planId, slotId, actionPath, card = null, iterations = 500) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/create-child-sim`, {
      action_path: actionPath,
      card,
      iterations,
    })
    return response.data
  },

  async linkSlotSim(planId, slotId, simId) {
    const response = await api.post(`/day-plans/${planId}/slots/${slotId}/link-sim`, {
      sim_id: simId,
    })
    return response.data
  },

  async updateSlot(planId, slotId, data) {
    const response = await api.put(`/day-plans/${planId}/slots/${slotId}`, data)
    return response.data
  },

  async getCompatibleSims(planId, slotId) {
    const response = await api.get(`/day-plans/${planId}/slots/${slotId}/compatible-sims`)
    return response.data
  },

  async getExistingSimsForConfig(planId, configIdx) {
    const response = await api.get(`/day-plans/${planId}/configs/${configIdx}/existing-sims`)
    return response.data
  },

  async deleteSim(simId) {
    const response = await api.delete(`/sims/${simId}`)
    return response.data
  },
}

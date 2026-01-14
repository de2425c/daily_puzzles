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

  // Turn Builder
  async getTreeActions(simId, path = 'r:0') {
    const response = await api.get(`/sims/${simId}/tree/actions`, { params: { path } })
    return response.data
  },

  async getTreeRanges(simId, path) {
    const response = await api.get(`/sims/${simId}/tree/ranges`, { params: { path } })
    return response.data
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
}

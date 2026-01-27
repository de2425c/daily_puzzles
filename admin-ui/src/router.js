import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import SpotReview from './views/SpotReview.vue'
import PuzzleList from './views/PuzzleList.vue'
import GenerateView from './views/GenerateView.vue'
import SimLibrary from './views/SimLibrary.vue'
import SimView from './views/SimView.vue'
import SimBrowser from './views/SimBrowser.vue'
import TurnBuilder from './views/TurnBuilder.vue'
import RiverBuilder from './views/RiverBuilder.vue'
import DayPlanCreator from './views/DayPlanCreator.vue'

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/day-plan/:date', name: 'DayPlanCreator', component: DayPlanCreator },
  { path: '/sims', name: 'SimLibrary', component: SimLibrary },
  { path: '/sims/:id', name: 'SimView', component: SimView },
  { path: '/sims/:id/browse', name: 'SimBrowser', component: SimBrowser },
  { path: '/sims/:id/build-turn', name: 'TurnBuilder', component: TurnBuilder },
  { path: '/sims/:id/build-river', name: 'RiverBuilder', component: RiverBuilder },
  { path: '/spots/:id', name: 'SpotReview', component: SpotReview },
  { path: '/puzzles', name: 'PuzzleList', component: PuzzleList },
  { path: '/generate', name: 'Generate', component: GenerateView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router

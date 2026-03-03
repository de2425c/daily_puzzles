import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import PuzzleReview from './views/PuzzleReview.vue'
import DayPlanCreator from './views/DayPlanCreator.vue'

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/day-plan/:date', name: 'DayPlanCreator', component: DayPlanCreator },
  { path: '/puzzles/:id/edit', name: 'PuzzleReview', component: PuzzleReview },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router

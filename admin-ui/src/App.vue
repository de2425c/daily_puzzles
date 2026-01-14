<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app">
    <header>
      <h1>Puzzle Admin</h1>
      <nav>
        <RouterLink to="/">Workflow</RouterLink>
        <RouterLink to="/sims">Sims</RouterLink>
        <RouterLink to="/generate">Generate</RouterLink>
      </nav>
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 20px;
  border-bottom: 1px solid #ddd;
}

header h1 {
  margin: 0;
  font-size: 24px;
}

nav {
  display: flex;
  gap: 20px;
}

nav a {
  color: #333;
  text-decoration: none;
  padding: 8px 16px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

nav a:hover {
  background-color: #f0f0f0;
}

nav a.router-link-exact-active {
  background-color: #007bff;
  color: white;
}
</style>

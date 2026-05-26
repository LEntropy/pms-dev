import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import naive from 'naive-ui'
import App from './App.vue'

import Login from './views/Login.vue'
import Dashboard from './views/Dashboard.vue'
import Patches from './views/Patches.vue'
import Policies from './views/Policies.vue'
import Deployments from './views/Deployments.vue'
import Endpoints from './views/Endpoints.vue'
import Reports from './views/Reports.vue'
import AuditLogs from './views/AuditLogs.vue'
import Admin from './views/Admin.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', component: Login, meta: { public: true } },
  { path: '/dashboard', component: Dashboard },
  { path: '/endpoints', component: Endpoints },
  { path: '/patches', component: Patches },
  { path: '/policies', component: Policies },
  { path: '/deployments', component: Deployments },
  { path: '/reports', component: Reports },
  { path: '/audit', component: AuditLogs },
  { path: '/admin', component: Admin },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('pms_access_token')
  if (!to.meta.public && !token) {
    return '/login'
  }
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)
app.mount('#app')

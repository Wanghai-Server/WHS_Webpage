import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import("../pages/home.vue"),
    meta: { titleKey: 'pageTitle.home'}
  },
  {
    path: '/about',
    name: 'About',
    component: () => import("../pages/about.vue"),
    meta: { titleKey: 'pageTitle.about'}
  },
  {
    path: '/news',
    name: 'News',
    component: () => import("../pages/news_platform.vue"),
    meta: { titleKey: 'pageTitle.news'}
  },
  {
    path: '/news/:id',
    name: 'NewsDetail',
    component: () => import("../pages/news_detail.vue"),
    meta: { titleKey: 'pageTitle.news'}
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import("../pages/login.vue"),
    meta: { titleKey: 'pageTitle.login'}
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router

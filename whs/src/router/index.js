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
  },
  {
    path: '/user/:uid',
    name: 'User',
    component: () => import("../pages/user.vue"),
    meta: { titleKey: 'pageTitle.user'}
  },
  {
    path: '/joinus',
    name: 'JoinUs',
    component: () => import("../pages/joinus.vue"),
    meta: { titleKey: 'pageTitle.joinus'}
  },
  {
    path: '/joinus/exam',
    name: 'Exam',
    component: () => import("../pages/exam.vue"),
    meta: { titleKey: 'pageTitle.joinus'}
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // 后退时恢复原位置；前进/新跳转回到页首
    return savedPosition || { top: 0 }
  }
})

export default router

import { createRouter, createWebHistory } from 'vue-router'
import { ensureSiteConfig } from '../composables/useSiteConfig'

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
    path: '/forum',
    name: 'Forum',
    component: () => import("../pages/forum/index.vue"),
    meta: { titleKey: 'pageTitle.forum'}
  },
  {
    path: '/wiki',
    name: 'Wiki',
    component: () => import("../pages/wiki/layout.vue"),
    meta: { titleKey: 'pageTitle.wiki'},
    children: [
      {
        path: '',
        name: 'WikiHome',
        component: () => import("../pages/wiki/index.vue"),
      },
      {
        path: 'page/:slug(.*)',
        name: 'WikiPage',
        component: () => import("../pages/wiki/page_view.vue"),
      },
      {
        // 新建页面：静态段（edit/:slug(.*) 需要斜杠，/wiki/edit 匹配不到）
        path: 'edit',
        name: 'WikiEditNew',
        component: () => import("../pages/wiki/page_editor.vue"),
      },
      {
        path: 'edit/:slug(.*)',
        name: 'WikiEdit',
        component: () => import("../pages/wiki/page_editor.vue"),
      },
      {
        path: 'history/:slug(.*)',
        name: 'WikiHistory',
        component: () => import("../pages/wiki/page_history.vue"),
      },
      {
        path: 'search',
        name: 'WikiSearch',
        component: () => import("../pages/wiki/search.vue"),
      },
      // wiki 下的未知子路径：重定向回维基首页（父级已匹配，不会触发全局 301）
      {
        path: ':pathMatch(.*)*',
        redirect: '/wiki',
      },
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import("../pages/login.vue"),
    meta: { titleKey: 'pageTitle.login'}
  },
  {
    path: '/search',
    name: 'Search',
    component: () => import("../pages/search.vue"),
    meta: { titleKey: 'pageTitle.search'}
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

// 非法链接（不存在的路由，matched 为空）统一跳转：
// 优先跳转到 whs_config 中 "301" 配置的目标 —— 以 http(s):// 开头视为外部链接
// （整页跳转），否则视为站内路由路径（replace 跳转，不留非法链接历史）；
// 未配置或配置无效时回退到根路由 /。
router.beforeEach(async (to) => {
  if (to.matched.length === 0) {
    const cfg = await ensureSiteConfig()
    const target = String(cfg['301'] || '').trim() || '/'
    if (/^https?:\/\//i.test(target)) {
      window.location.replace(target)
      return false
    }
    if (target !== to.path) {
      return { path: target, replace: true }
    }
    return { path: '/', replace: true }
  }
  return true
})

export default router

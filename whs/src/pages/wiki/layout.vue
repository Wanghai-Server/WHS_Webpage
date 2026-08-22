<script setup>
/**
 * 维基公共骨架：站点导航 + 内容区 + 页脚。
 *
 * 持有全站唯一的页面清单（provide 供首页复用），路由变化时静默刷新，
 * 保证首页分组 / 最近更新 / 今日词条始终与后端一致。
 */
import { ref, provide, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import Top_navbar from '../../components/top_navbar.vue'
import Page_footer from '../../components/page_footer.vue'
import { wikiApi } from '../../composables/wiki/api.js'

const route = useRoute()

const pages = ref([])

async function loadPages() {
  try {
    const data = await wikiApi.listPages()
    pages.value = data.pages || []
  } catch {
    /* 后端不可用时保持空目录 */
  }
}

provide('wikiPages', pages)
provide('wikiRefreshPages', loadPages)

onMounted(loadPages)

// 路由变化：刷新页面清单（内容变更后首页数据同步）
watch(
  () => route.path,
  () => {
    loadPages()
  }
)
</script>

<template>
  <div class="wiki-layout">
    <Top_navbar />

    <main class="wiki-body">
      <router-view />
    </main>

    <Page_footer />
  </div>
</template>

<style scoped>
.wiki-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* 全宽内容区：阅读页大纲可贴屏幕右缘；各页面自行居中与内边距 */
.wiki-body {
  flex: 1;
  width: 100%;
  margin: 96px 0 0;
  padding: 0 0 48px;
  box-sizing: border-box;
}

@media (max-width: 1023px) {
  .wiki-body {
    margin-top: 88px;
  }
}
</style>

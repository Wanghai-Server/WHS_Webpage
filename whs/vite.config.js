import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// BlueMap 网页端在本地开发时由 8100 端口提供，生产环境由 nginx 反代
const bluemap = {
  target: 'http://127.0.0.1:8100',
  changeOrigin: true,
  rewrite: (path) => path.replace(/^\/map3d/, ''),
  ws: true,
}

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:7777',
      '/map3d': bluemap,
    },
    allowedHosts: ['h1.getmc.cn'],
  },
  preview: {
    proxy: {
      '/api': 'http://127.0.0.1:7777',
      '/map3d': bluemap,
    },
    allowedHosts: ['h1.getmc.cn', 'wanghaiserver.top'],
  }
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:7777'
    },
    allowedHosts: ['h1.getmc.cn'],
  },
  preview: {
    proxy: {
      '/api': 'http://127.0.0.1:7777'
    },
    allowedHosts: ['h1.getmc.cn', 'wanghaiserver.top'],
  }
})

import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { inspectAttr } from 'kimi-plugin-inspect-react'

// https://vite.dev/config/
export default defineConfig({
  // 必须用绝对根路径：FastAPI 从 "/" 提供 SPA 时，深链（如 /leagues/1）下
  // 相对路径 "./assets/…" 会被解析成 /leagues/assets/… → 命中 SPA 回落返回 index.html
  // → 浏览器报 "Failed to load module script: Expected a JavaScript module …"（白屏）
  base: "/",
  plugins: [inspectAttr(), react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    // 后端 FastAPI（8000）挂在同源的 /api 下：队徽代理 /api/ui/logo/<id> 用相对路径，离线也能出图
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
    watch: {
      // 编辑器/工具链的原子写入会在源码树里留临时目录，fs watcher 遇到会 EBUSY 直接崩
      ignored: ["**/node_modules/**", "**/.*.tmpdir/**", "**/*.tmp", "**/dist/**"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});

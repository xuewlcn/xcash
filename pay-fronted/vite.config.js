import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { fileURLToPath, URL } from 'node:url'
import { payMockPlugin } from "./mock/mockPlugin.js"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), payMockPlugin()],
  base: '/static/pay/',
  build: {
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})

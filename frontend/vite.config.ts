import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 중(npm run dev)에는 /api 요청을 FastAPI 앱 서버로 넘깁니다.
const apiTarget = process.env.API_TARGET ?? 'http://127.0.0.1:8501'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': apiTarget },
  },
})

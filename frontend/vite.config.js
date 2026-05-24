import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    host: true,
    proxy: {
      '/ask': 'http://localhost:5051',
      '/upload_file': 'http://localhost:5051',
      '/export_docx': 'http://localhost:5051',
      '/export_summary': 'http://localhost:5051',
      '/latest_export': 'http://localhost:5051',
      '/health': 'http://localhost:5051',
      '/reports': 'http://localhost:5051',
      '/exports': 'http://localhost:5051',
      '/submit_feedback': 'http://localhost:5051',
      '/audit': 'http://localhost:5051',
      '/stream': 'http://localhost:5051',
    }
  }
})

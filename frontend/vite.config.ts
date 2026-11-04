import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The back end's CORS list names this origin, so the port must not drift.
    port: 5173,
    strictPort: true,
    // This project lives in a OneDrive folder, where file-change events are unreliable;
    // polling catches every save.
    watch: { usePolling: true, interval: 300 },
  },
})

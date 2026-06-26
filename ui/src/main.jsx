import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Bundled fonts (offline-safe in the packaged app — no Google Fonts CDN).
import '@fontsource/inter/300.css'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'
import './index.css'
// Ambi Light design system (scoped under .ambi-root) — imported after index.css
// so the new look wins where it overlaps the legacy Tailwind base.
import './styles/ds.css'
import './styles/pages.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

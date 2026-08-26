import React from 'react'
import ReactDOM from 'react-dom/client'
import 'maplibre-gl/dist/maplibre-gl.css'
import './styles.css'
import App from './App'
import { I18nProvider } from './i18n'

// Offline shell + push delivery: register unconditionally at boot.
// Opt-in gating lives in lib/pushClient (browser alerts); registration
// itself is harmless and enables the offline app shell immediately.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* dev server without SW support, private mode: app still works */
    })
  })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>,
)

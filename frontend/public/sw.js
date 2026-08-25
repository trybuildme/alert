// NOAH service worker: Web Push delivery + notification focus routing.
// Registered by the notification bell only after the user opts in to
// browser alerts (registration itself is harmless and happens on load).

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { title: 'NOAH alert', body: event.data ? event.data.text() : '' }
  }
  const severity = data.severity || 'INFO'
  event.waitUntil(self.registration.showNotification(data.title || `NOAH ${severity} hazard alert`, {
    body: data.summary || data.body || '',
    tag: data.event_uid || 'noah-alert',
    renotify: true,
    requireInteraction: severity === 'CRITICAL' || severity === 'HIGH',
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    data: { url: self.registration.scope },
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if ('focus' in client) return client.focus()
        }
        return self.clients.openWindow(url)
      }),
  )
})

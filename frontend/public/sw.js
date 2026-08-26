// NOAH service worker: Web Push delivery, notification focus routing,
// and offline support.
//
// Offline strategy:
//   * App shell ('/', '/index.html'): network-first with cache fallback
//     — fresh deploy wins when online, cached shell renders offline.
//   * Hashed build assets (/assets/*): stale-while-revalidate. Filenames
//     are content-hashed so a cached hit is always correct.
//   * Map tiles (/tiles/*): cache-first (immutable imagery), capped via
//     simple LRU trim so the Cache API doesn't grow without bound.
//   * GET /api/* reads: network-first with cache fallback — last known
//     earthquakes/statistics stay visible when the backend is unreachable.
//   * Everything else (POSTs, SSE, external): network only.
//
// Registration is unconditional at app boot (main.tsx); push opt-in is
// a separate concern handled by lib/pushClient.

const SHELL_CACHE = 'noah-shell-v1'
const ASSET_CACHE = 'noah-assets-v1'
const TILE_CACHE = 'noah-tiles-v1'
const API_CACHE = 'noah-api-v1'
const MAX_TILES = 400
const MAX_API_ENTRIES = 60

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE)
    try {
      await cache.add(new Request('/', { cache: 'reload' }))
    } catch { /* first run offline: nothing to precache yet */ }
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys()
    await Promise.all(
      names.filter((n) => n.startsWith('noah-') &&
        ![SHELL_CACHE, ASSET_CACHE, TILE_CACHE, API_CACHE].includes(n))
        .map((n) => caches.delete(n)))
    await self.clients.claim()
  })())
})

async function trimCache(name, max) {
  const cache = await caches.open(name)
  const keys = await cache.keys()
  if (keys.length <= max) return
  // Keys arrive oldest-insert-first; delete the head.
  for (const key of keys.slice(0, keys.length - max)) {
    await cache.delete(key)
  }
}

async function networkFirst(request, cacheName, fallbackUrl = null) {
  const cache = await caches.open(cacheName)
  try {
    const resp = await fetch(request)
    if (resp.ok) cache.put(request, resp.clone())
    return resp
  } catch {
    const hit = await cache.match(request) ??
      (fallbackUrl ? await cache.match(fallbackUrl) : null)
    if (hit) return hit
    return new Response(JSON.stringify({ source: 'unavailable', offline: true }), {
      status: 503, headers: { 'Content-Type': 'application/json' },
    })
  }
}

async function cacheFirst(request, cacheName, max) {
  const cache = await caches.open(cacheName)
  const hit = await cache.match(request)
  if (hit) return hit
  try {
    const resp = await fetch(request)
    if (resp.ok) {
      cache.put(request, resp.clone())
      if (max) trimCache(cacheName, max)
    }
    return resp
  } catch {
    return new Response('', { status: 504 })
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName)
  const hit = await cache.match(request)
  const refresh = fetch(request).then((resp) => {
    if (resp.ok) cache.put(request, resp.clone())
    return resp
  }).catch(() => null)
  return hit ?? (await refresh) ?? new Response('', { status: 504 })
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return

  if (event.request.mode === 'navigate' || url.pathname === '/') {
    event.respondWith(networkFirst(event.request, SHELL_CACHE, '/'))
    return
  }
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(staleWhileRevalidate(event.request, ASSET_CACHE))
    return
  }
  if (url.pathname.startsWith('/tiles/')) {
    event.respondWith(cacheFirst(event.request, TILE_CACHE, MAX_TILES))
    return
  }
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(event.request, API_CACHE))
    trimCache(API_CACHE, MAX_API_ENTRIES)
  }
})

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

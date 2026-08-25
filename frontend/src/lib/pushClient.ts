// Browser Web Push subscription management for NOAH alerts.
// Talks to /api/push/*; the VAPID public key must be configured on the
// backend or enableBrowserAlerts reports 'unconfigured'.

export interface PushState {
  supported: boolean
  enabled: boolean
  unconfigured: boolean
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const normalized = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(normalized)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

async function registration(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register('/sw.js')
}

export async function currentPushState(): Promise<PushState> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    return { supported: false, enabled: false, unconfigured: false }
  }
  try {
    const res = await fetch('/api/push/vapid')
    if (!res.ok) return { supported: true, enabled: false, unconfigured: true }
    const { public_key } = await res.json()
    if (!public_key) {
      return { supported: true, enabled: false, unconfigured: true }
    }
    const reg = await registration()
    const sub = await reg.pushManager.getSubscription()
    return { supported: true, enabled: !!sub, unconfigured: false }
  } catch {
    return { supported: false, enabled: false, unconfigured: false }
  }
}

export async function enableBrowserAlerts(): Promise<'granted' | 'denied' | 'error'> {
  try {
    const res = await fetch('/api/push/vapid')
    const { public_key } = await res.json()
    if (!public_key) return 'error'
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return 'denied'
    const reg = await registration()
    let sub = await reg.pushManager.getSubscription()
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      })
    }
    const json = sub.toJSON() as { endpoint?: string; keys?: Record<string, string> }
    const post = await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
    })
    return post.ok ? 'granted' : 'error'
  } catch {
    return 'error'
  }
}

export async function disableBrowserAlerts(): Promise<boolean> {
  try {
    const reg = await registration()
    const sub = await reg.pushManager.getSubscription()
    if (sub) {
      const endpoint = sub.endpoint
      await sub.unsubscribe()
      await fetch('/api/push/unsubscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint }),
      })
    }
    return true
  } catch {
    return false
  }
}

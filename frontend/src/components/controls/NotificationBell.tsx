// Facebook-style notification bell for the top bar: unread badge +
// dropdown feed (earthquake alerts, new cyclones; tsunami/flood slots
// activate when those modules exist) + browser push opt-in.

import { useEffect, useState } from 'react'
import { useNotifStore, type NotifKind } from '../../stores/notifications'
import { currentPushState, disableBrowserAlerts, enableBrowserAlerts, type PushState } from '../../lib/pushClient'
import { useI18n } from '../../i18n'

const KIND_META: Record<NotifKind, { icon: string; color: string; label: string }> = {
  earthquake: { icon: '🌍', color: '#ff9800', label: 'Earthquake' },
  cyclone: { icon: '🌀', color: '#38bdf8', label: 'Cyclone' },
  tsunami: { icon: '🌊', color: '#22d3ee', label: 'Tsunami' },
  flood: { icon: '💧', color: '#1e88e5', label: 'Flood' },
}

function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'now'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

export default function NotificationBell() {
  const open = useNotifStore((s) => s.open)
  const items = useNotifStore((s) => s.items)
  const unread = useNotifStore((s) => s.unread)
  const toggle = useNotifStore((s) => s.toggle)
  const markAllRead = useNotifStore((s) => s.markAllRead)
  const [push, setPush] = useState<PushState | null>(null)
  const [pushBusy, setPushBusy] = useState(false)
  const { t } = useI18n()

  // Probe push capability lazily when the dropdown first opens so we
  // don't fire /api/push/vapid on every page load.
  useEffect(() => {
    if (open && push === null) {
      currentPushState().then(setPush).catch(() => setPush({
        supported: false, enabled: false, unconfigured: false,
      }))
    }
  }, [open, push])

  return (
    <div className="notif-wrap">
      <button
        className={`notif-btn ${unread > 0 ? 'has-unread' : ''}`}
        onClick={toggle}
        title={t('notif.bellLabel')}
        aria-label={`${t('notif.bellLabel')}${unread ? ` (${unread} unread)` : ''}`}
      >
        <svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden>
          <path d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-5v-1l-1.6-1.8a2 2 0 0 1-.5-1.33V9.5a4.9 4.9 0 0 0-3.9-4.8V4a1 1 0 1 0-2 0v.7a4.9 4.9 0 0 0-3.9 4.8v3.37a2 2 0 0 1-.5 1.32L5 16v1Z"/>
        </svg>
        {unread > 0 && <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>}
      </button>

      {open && (
        <div className="notif-drop">
          <div className="notif-head">
            <span>{t('notif.title')}</span>
            {items.length > 0 && (
              <button className="notif-clear" onClick={markAllRead}>{t('notif.markAllRead')}</button>
            )}
          </div>
          {items.length === 0 && (
            <div className="notif-empty">{t('notif.empty')}</div>
          )}
          {items.map((n) => {
            const meta = KIND_META[n.kind]
            return (
              <div key={n.id} className={`notif-item ${n.read ? '' : 'unread'}`}>
                <span
                  className="notif-kind-dot"
                  style={{ background: n.severity && KIND_META[n.kind].icon === '🌍'
                    ? severityColor(n.severity) : meta.color }}
                >
                  {meta.icon}
                </span>
                <span className="notif-body">
                  <b>{n.title}</b>
                  {n.detail && <span className="notif-detail">{n.detail}</span>}
                </span>
                <span className="notif-age">{ago(n.at)}</span>
              </div>
            )
          })}
          {push && push.supported && !push.unconfigured && (
            <div className="notif-push">
              <span className="notif-push-label">{t('notif.browserAlerts')}</span>
              <button
                className={`notif-push-btn ${push.enabled ? 'on' : ''}`}
                disabled={pushBusy}
                onClick={async () => {
                  setPushBusy(true)
                  if (push.enabled) {
                    await disableBrowserAlerts()
                    setPush({ ...push, enabled: false })
                  } else {
                    const result = await enableBrowserAlerts()
                    if (result === 'granted') setPush({ ...push, enabled: true })
                  }
                  setPushBusy(false)
                }}
                title={push.enabled
                  ? 'Subscribed — click to stop browser notifications'
                  : 'Get OS notifications for hazard alerts even when NOAH is closed'}
              >
                {pushBusy ? '…' : push.enabled ? 'ON' : 'OFF'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function severityColor(severity: string): string {
  const map: Record<string, string> = {
    INFO: '#38bdf8', LOW: '#00e400', MODERATE: '#ffe400',
    HIGH: '#ff9800', CRITICAL: '#ff2020',
  }
  return map[severity] ?? '#888'
}

// NotificationBell component tests: unread badge, dropdown feed,
// mark-all-read, empty state. pushClient is stubbed so tests don't
// touch service workers or /api/push.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../../lib/pushClient', () => ({
  currentPushState: vi.fn(async () =>
    ({ supported: false, enabled: false, unconfigured: false })),
  enableBrowserAlerts: vi.fn(async () => 'granted'),
  disableBrowserAlerts: vi.fn(async () => true),
}))

import { useNotifStore, type NotifItem } from '../../stores/notifications'
import { I18nProvider } from '../../i18n'
import NotificationBell from './NotificationBell'

const renderBell = () =>
  render(<I18nProvider><NotificationBell /></I18nProvider>)

const ITEMS: NotifItem[] = [
  { id: 'eq:usgs:1', kind: 'earthquake', severity: 'HIGH',
    title: 'M5.8 — 12 km NE of Lucban', at: new Date(Date.now() - 120_000).toISOString() },
  { id: 'cyclone:ibtracs:9', kind: 'cyclone',
    title: 'New cyclone: Bagyo', detail: 'Tropical Storm', at: new Date().toISOString() },
]

beforeEach(() => {
  useNotifStore.setState({ open: false, items: [], unread: 0 })
})

describe('NotificationBell', () => {
  it('shows an unread badge and accessible label while items are unread', () => {
    useNotifStore.setState({ items: ITEMS, unread: 2 })
    renderBell()
    expect(screen.getByRole('button', { name: /2 unread/ })).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('caps the badge at "9+"', () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      id: `x${i}`, kind: 'earthquake' as const,
      title: `t${i}`, at: new Date().toISOString(),
    }))
    useNotifStore.setState({ items: many, unread: 12 })
    renderBell()
    expect(screen.getByText('9+')).toBeInTheDocument()
  })

  it('opens a dropdown listing notifications and clears the badge', async () => {
    const user = userEvent.setup()
    useNotifStore.setState({ items: ITEMS, unread: 2 })
    renderBell()
    await user.click(screen.getByRole('button', { name: /unread/ }))
    expect(screen.getByText('NOTIFICATIONS')).toBeInTheDocument()
    expect(screen.getByText('M5.8 — 12 km NE of Lucban')).toBeInTheDocument()
    expect(screen.getByText(/New cyclone/)).toBeInTheDocument()
    expect(useNotifStore.getState().unread).toBe(0)
  })

  it('shows the empty state when there is nothing in the feed', async () => {
    const user = userEvent.setup()
    renderBell()
    await user.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(screen.getByText('No notifications yet.')).toBeInTheDocument()
    expect(screen.queryByText('Mark all read')).not.toBeInTheDocument()
  })

  it('marks all read via the header button without closing the dropdown', async () => {
    const user = userEvent.setup()
    useNotifStore.setState({ open: true, items: ITEMS, unread: 2 })
    renderBell()
    await user.click(screen.getByText('Mark all read'))
    expect(useNotifStore.getState().unread).toBe(0)
    expect(useNotifStore.getState().open).toBe(true)
    expect(useNotifStore.getState().items.every((i) => i.read)).toBe(true)
  })

  it('hides the browser-alerts toggle when push is unsupported', async () => {
    const user = userEvent.setup()
    renderBell()
    await user.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(screen.queryByText('Browser alerts')).not.toBeInTheDocument()
  })
})

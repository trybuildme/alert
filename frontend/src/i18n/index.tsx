// Minimal Filipino (Tagalog) i18n layer for the NOAH UI chrome.
//
// Design constraints:
//   * No dependency — a flat dictionary + React context beats pulling
//     i18next into a map-first bundle we just spent a release shaving.
//   * Chrome-only scope: panel titles, control labels, aria strings.
//     Layer names/descriptions are data (stores/index.ts) and stay
//     English for now; the dictionary below is the extension point.
//   * t() falls back to English, then to the key itself, so a missing
//     translation can never blank out UI.
//   * Choice persists in localStorage ('noah.lang'); default is
//     English so existing users see no change.

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

export type Lang = 'en' | 'fil'

const STORAGE_KEY = 'noah.lang'

type Entry = { en: string; fil: string }

export const DICT: Record<string, Entry> = {
  // Top bar
  'topbar.basemap': { en: 'BASE MAP', fil: 'BATAYANG MAPA' },
  'topbar.satellite': { en: 'SATELLITE', fil: 'SATELITE' },
  'topbar.hazard': { en: 'HAZARD', fil: 'PELIGRO' },
  'topbar.tropical': { en: 'TROPICAL', fil: 'TROPIKAL' },
  'topbar.quakes': { en: 'Quakes', fil: 'Lindol' },
  'topbar.replay': { en: 'Replay', fil: 'I-replay' },
  'topbar.cyclone7day': { en: 'Cyclone 7-Day', fil: 'Bagyo 7-Araw' },
  'topbar.enhanced': { en: 'Enhanced', fil: 'Pinahusay' },
  'topbar.mode3d': { en: '3D EARTH', fil: '3D DAIGDIG' },
  'topbar.mode2d': { en: '2D MAP', fil: '2D MAPA' },
  'topbar.language': { en: 'WIKA', fil: 'LANGUAGE' },
  'search.placeholder': { en: 'Search place or lat, lon …', fil: 'Hanapin ang lugar o lat, lon …' },

  // Layer panel
  'layers.title': { en: 'LAYERS', fil: 'MGA PATONG' },
  'layers.opacity': { en: 'Opacity', fil: 'Kalabuan' },
  'layers.raise': { en: 'Raise', fil: 'Itaas' },
  'layers.lower': { en: 'Lower', fil: 'Ibaba' },

  // Notifications
  'notif.title': { en: 'NOTIFICATIONS', fil: 'MGA ABISO' },
  'notif.markAllRead': { en: 'Mark all read', fil: 'Tandasan lahat bilang nabasa' },
  'notif.empty': { en: 'No notifications yet.', fil: 'Wala pang abiso.' },
  'notif.browserAlerts': { en: 'Browser alerts', fil: 'Mga alerto sa browser' },
  'notif.bellLabel': { en: 'Notifications', fil: 'Mga abiso' },

  // Replay transport
  'replay.playTitle': { en: 'Play replay', fil: 'I-play ang replay' },
  'replay.pauseTitle': { en: 'Pause replay', fil: 'Ihinto ang replay' },
  'replay.exitTitle': { en: 'Exit replay (returns to live feed)', fil: 'Labas sa replay (babalik sa live)' },
  'replay.windowTitle': { en: 'History window to replay', fil: 'Lawak ng kasaysayan na i-re-replay' },
  'replay.speedTitle': { en: 'Playback speed', fil: 'Bilis ng pag-playback' },
  'replay.loading': { en: 'loading…', fil: 'naglo-load…' },
  'replay.events': { en: 'events', fil: 'kaganapan' },

  // Volcano assessment
  'volcano.assessment': { en: 'Assessment', fil: 'Pagtataya' },
  'volcano.basis': { en: 'Basis', fil: 'Batayan' },

  // App boot
  'app.booting': { en: 'Initializing NOAH …', fil: 'Binubuksan ang NOAH …' },
}

function initialLang(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'fil' ? 'fil' : 'en'
  } catch {
    return 'en'
  }
}

interface I18nCtx {
  lang: Lang
  setLang: (l: Lang) => void
  toggle: () => void
  t: (key: string) => string
}

const Ctx = createContext<I18nCtx | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem(STORAGE_KEY, l)
    } catch { /* private mode: session-only */ }
  }, [])

  const toggle = useCallback(() => {
    setLangState((cur) => {
      const next: Lang = cur === 'en' ? 'fil' : 'en'
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch { /* ignore */ }
      return next
    })
  }, [])

  const t = useCallback(
    (key: string) => DICT[key]?.[lang] ?? DICT[key]?.en ?? key,
    [lang],
  )

  const value = useMemo(() => ({ lang, setLang, toggle, t }), [lang, setLang, toggle, t])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18nCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}

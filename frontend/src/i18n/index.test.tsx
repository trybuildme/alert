// i18n layer tests: dictionary lookup, English fallback, language
// toggle + localStorage persistence.

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { DICT, I18nProvider, useI18n } from './index'

function Probe() {
  const { t, lang, toggle } = useI18n()
  return (
    <div>
      <span data-testid="lang">{lang}</span>
      <span data-testid="known">{t('layers.title')}</span>
      <span data-testid="missing">{t('no.such.key')}</span>
      <button onClick={toggle}>toggle</button>
    </div>
  )
}

describe('i18n', () => {
  it('defaults to English and resolves known keys', () => {
    const { unmount } = render(<I18nProvider><Probe /></I18nProvider>)
    expect(screen.getByTestId('lang')).toHaveTextContent('en')
    expect(screen.getByTestId('known')).toHaveTextContent(DICT['layers.title'].en)
    expect(screen.getByTestId('missing')).toHaveTextContent('no.such.key')
    unmount()
  })

  it('toggles to Filipino, translates, and persists the choice', async () => {
    const user = userEvent.setup()
    const first = render(<I18nProvider><Probe /></I18nProvider>)
    await user.click(screen.getByText('toggle'))
    expect(screen.getByTestId('lang')).toHaveTextContent('fil')
    expect(screen.getByTestId('known')).toHaveTextContent(
      DICT['layers.title'].fil)
    expect(localStorage.getItem('alert.lang')).toBe('fil')
    first.unmount()

    // A fresh provider hydrates the persisted choice.
    const second = render(<I18nProvider><Probe /></I18nProvider>)
    expect(second.getByTestId('lang')).toHaveTextContent('fil')
    second.unmount()
  })
})

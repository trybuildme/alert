// Vitest global setup for component tests.
// - jest-dom matchers (toBeInTheDocument, toBeDisabled, …)
// - localStorage is wiped between tests so layer-snapshot hydration
//   in stores/index.ts starts from INITIAL_LAYERS every time.
import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'

beforeEach(() => {
  localStorage.clear()
})

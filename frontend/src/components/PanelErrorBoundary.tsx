// Minimal error boundary: one broken panel must never blank the whole
// NOAH app (a render-time throw in an unbounded subtree unmounts the
// React root — that took the entire map down when the elevation panel
// hit a malformed payload).

import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Shown in place of the crashed subtree. */
  label?: string
}

interface State {
  error: Error | null
}

export default class PanelErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    // eslint-disable-next-line no-console
    console.error('[noah] panel crash:', this.props.label ?? 'panel', error.message)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="panel-crash" role="alert">
          ⚠ {this.props.label ?? 'Panel'} failed to render —{' '}
          {this.state.error.message}
        </div>
      )
    }
    return this.props.children
  }
}

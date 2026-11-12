import { useEffect, useState } from 'react'
import { getHealth } from '../api'

export default function ConnectionCheck() {
  const [connection, setConnection] = useState<
    'checking' | 'connected' | 'error'
  >('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) setConnection('connected')
      })
      .catch(() => {
        if (!controller.signal.aborted) setConnection('error')
      })
    return () => controller.abort()
  }, [attempt])

  return (
    <section className="health-check" aria-label="Connection check">
      <p role="status" aria-atomic="true" data-state={connection}>
        <span className="status-dot" aria-hidden="true" />
        {connection === 'checking' && 'Checking the API connection…'}
        {connection === 'connected' &&
          'API connected. You’re ready to explore.'}
        {connection === 'error' &&
          'Connection check failed. Make sure the backend is running, then try again.'}
      </p>
      <button
        className="button-text"
        type="button"
        disabled={connection === 'checking'}
        onClick={() => {
          setConnection('checking')
          setAttempt((previous) => previous + 1)
        }}
      >
        {connection === 'checking' ? 'Checking…' : 'Check again'}
      </button>
    </section>
  )
}

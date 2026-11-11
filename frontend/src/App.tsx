import { useEffect, useState } from 'react'
import { getHealth } from './api'

type ConnectionState = 'checking' | 'connected' | 'error'

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>('checking')
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

  function checkAgain() {
    setConnection('checking')
    setAttempt((previous) => previous + 1)
  }

  return (
    <div className="page">
      <header className="page-header">
        <span className="brand-mark" aria-hidden="true">SH</span>
        <p>A project for students in Kazakhstan</p>
      </header>

      <main>
        <section className="introduction" aria-labelledby="project-title">
          <h1 id="project-title">Scholarship Hunter AI</h1>
          <p className="lead">A clearer path to a funded master’s.</p>
          <p>
            We’re building a way to discover scholarships abroad, understand
            eligibility, and compare opportunities using official sources.
          </p>
          <p className="scope-note">
            This first version establishes the application foundation.
            Scholarship search and recommendations will follow in later phases.
          </p>
        </section>

        <section className="connection-panel" aria-labelledby="connection-title">
          <h2 id="connection-title">Connection check</h2>
          <p className="connection-status" data-state={connection} role="status" aria-atomic="true">
            <span className="status-dot" aria-hidden="true" />
            {connection === 'checking' && 'Checking the API connection…'}
            {connection === 'connected' && 'API connected. The application foundation is ready.'}
            {connection === 'error' && 'Connection check failed. Make sure the backend is running, then try again.'}
          </p>
          <button type="button" onClick={checkAgain} disabled={connection === 'checking'}>
            {connection === 'checking' ? 'Checking…' : 'Check again'}
          </button>
        </section>
      </main>

      <footer>Built with care for the next chapter of your education.</footer>
    </div>
  )
}

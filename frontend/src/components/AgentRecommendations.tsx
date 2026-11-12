import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchAgentRecommendations } from '../agent'
import type { AgentResponse } from '../agent'
import type { RankedProgramme, StudentProfile } from '../types'
import { calendarDate } from '../display'
import { Assessment, SourceLink } from './ui'

type State =
  | { status: 'idle' | 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; response: AgentResponse }

export default function AgentRecommendations({
  profile,
}: {
  profile: StudentProfile
}) {
  const [goal, setGoal] = useState(
    'Find scholarship candidates for my profile and show what needs verification.',
  )
  const [state, setState] = useState<State>({ status: 'idle' })
  const [validationError, setValidationError] = useState('')
  const controller = useRef<AbortController | null>(null)
  const goalInput = useRef<HTMLTextAreaElement>(null)

  useEffect(() => () => controller.current?.abort(), [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (state.status === 'loading') return
    const trimmed = goal.trim()
    if (!trimmed || trimmed.length > 300) {
      setValidationError('Describe your request using 1–300 characters.')
      goalInput.current?.focus()
      return
    }
    setValidationError('')
    controller.current?.abort()
    const pending = new AbortController()
    controller.current = pending
    setState({ status: 'loading' })
    try {
      const response = await fetchAgentRecommendations(
        profile,
        trimmed,
        pending.signal,
      )
      if (!pending.signal.aborted) setState({ status: 'ready', response })
    } catch (error) {
      if (!pending.signal.aborted)
        setState({
          status: 'error',
          message:
            error instanceof Error
              ? error.message
              : 'The local AI request could not be completed.',
        })
    }
  }

  const loading = state.status === 'loading'
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="breadcrumb">
            <a href="#/profile">My profile</a> / Local AI
          </p>
          <h1>Local AI recommendations</h1>
          <p>
            Let the local model explore the catalogue. Deterministic checks
            remain the authority on eligibility.
          </p>
        </div>
        <a className="button button-secondary" href="#/matches">
          Use deterministic matches
        </a>
      </div>
      <p className="notice">
        Your profile and request stay within this local application and Ollama.
        No cloud inference or profile storage. Do not include names, contact
        details, documents, or other sensitive information.
      </p>
      <form
        className="agent-form content-panel"
        onSubmit={submit}
        noValidate
        aria-busy={loading}
      >
        <div className="field">
          <label htmlFor="agent-goal">What would you like to find?</label>
          <textarea
            id="agent-goal"
            ref={goalInput}
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            maxLength={300}
            rows={3}
            disabled={loading}
            required
            aria-invalid={Boolean(validationError)}
            aria-describedby={
              validationError
                ? 'agent-goal-hint agent-goal-error'
                : 'agent-goal-hint'
            }
          />
          <small id="agent-goal-hint">
            Up to 300 characters. Qwen chooses up to 8 tool calls across 4
            steps; it cannot change eligibility rules.
          </small>
          {validationError && (
            <p className="field-error" id="agent-goal-error" role="alert">
              {validationError}
            </p>
          )}
        </div>
        <button type="submit" disabled={loading}>
          {loading ? 'Local AI is working…' : 'Generate AI recommendations'}
        </button>
      </form>
      {loading && (
        <p role="status" className="notice">
          The local model is exploring with tools. This can take up to 90
          seconds. You can leave this page to cancel waiting; the local
          inference may finish within its server limits.
        </p>
      )}
      {state.status === 'error' && (
        <section className="state-panel error-panel" role="alert">
          <h2>Local AI is unavailable</h2>
          <p>{state.message}</p>
          <p>The catalogue and deterministic eligibility checks still work.</p>
          <a className="button button-secondary" href="#/matches">
            Continue with deterministic matches
          </a>
        </section>
      )}
      {state.status === 'ready' && <AgentOutput response={state.response} />}
    </>
  )
}

function AgentOutput({ response }: { response: AgentResponse }) {
  return (
    <section className="agent-output" aria-label="Local AI response">
      <div className="notice">
        <h2>
          {response.status === 'completed'
            ? 'Source-backed results'
            : response.status === 'limit_reached'
              ? 'Exploration limit reached'
              : response.status === 'no_matches'
                ? 'No recommendations selected'
                : 'Further verification needed'}
        </h2>
        <p>{response.message}</p>
        <p>{response.disclaimer}</p>
      </div>
      {response.warnings.length > 0 && (
        <section className="agent-warnings">
          <h3>Important limitations</h3>
          <ul>
            {response.warnings.map((warning, index) => (
              <li key={`${index}:${warning}`}>{warning}</li>
            ))}
          </ul>
        </section>
      )}
      {response.recommendations.map((item) => (
        <ProgrammeResult item={item} key={item.assessment.scholarship_id} />
      ))}
      {response.recommendations.length === 0 && (
        <p>
          No grounded recommendation was returned. Try a simpler request or use{' '}
          <a href="#/matches">deterministic matches</a>.
        </p>
      )}
      {Boolean(response.fallback_recommendations?.length) && (
        <section aria-labelledby="fallback-heading">
          <h2 id="fallback-heading">Deterministic candidates to verify</h2>
          <p>{response.fallback_reason}</p>
          {response.fallback_recommendations?.map((item) => (
            <ProgrammeResult item={item} key={item.assessment.scholarship_id} />
          ))}
        </section>
      )}
      <section className="agent-trace content-panel">
        <h2>Tools actually attempted</h2>
        <p>
          Model: {response.model}. {response.steps} of 4 steps;{' '}
          {response.tool_calls} of 8 tool calls. Evaluated{' '}
          {calendarDate(response.evaluated_on)} (UTC).
        </p>
        {response.tool_trace.length ? (
          <ol>
            {response.tool_trace.map((item, index) => (
              <li key={index}>
                <h3>
                  Step {item.step}: {item.name.replaceAll('_', ' ')}
                </h3>
                <p>
                  <strong>
                    {item.status === 'ok'
                      ? 'Executed'
                      : item.status.replaceAll('_', ' ')}
                  </strong>{' '}
                  — {item.summary}
                </p>
                {item.source_url && (
                  <p>
                    <SourceLink
                      url={item.source_url}
                      label="Fetched official source"
                    />
                    {item.fetched_at && ` · Fetched ${item.fetched_at}`}
                  </p>
                )}
              </li>
            ))}
          </ol>
        ) : (
          <p>No tool calls were executed.</p>
        )}
      </section>
    </section>
  )
}

function ProgrammeResult({ item }: { item: RankedProgramme }) {
  return (
    <article className="content-panel">
      <Assessment result={item.assessment} />
      <h3>Ranking explanation</h3>
      <ul>
        {item.ranking_reasons.map((reason, index) => (
          <li key={`${index}:${reason}`}>
            {reason
              .replaceAll('needs_verification', 'needs verification')
              .replaceAll('fully_funded', 'fully funded')
              .replaceAll('partially_funded', 'partially funded')}
          </li>
        ))}
      </ul>
    </article>
  )
}

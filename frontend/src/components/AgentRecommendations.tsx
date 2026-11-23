import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchAgentRecommendations } from '../agent'
import type { AgentResponse, RequestPreferenceCheck } from '../agent'
import type { RankedProgramme, RequirementResult, StudentProfile } from '../types'
import { calendarDate } from '../display'
import { Assessment, SourceLink } from './ui'

type State =
  | { status: 'idle' | 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; response: AgentResponse }

const responseHeadings: Record<AgentResponse['status'], string> = {
  completed: 'Source-backed results',
  needs_verification: 'Further verification needed',
  limit_reached: 'Exploration limit reached',
  no_matches: 'No recommendations selected',
  model_error: 'Local AI could not finish',
  ambiguous_match: 'Choose a programme',
}

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
      <div className="page-heading agent-heading">
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
      <div className="agent-workspace">
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
              Up to 300 characters. Try “Scholarships in Germany, including
              partial funding” or “Only partially funded scholarships in Japan.”
            </small>
            {validationError && (
              <p className="field-error" id="agent-goal-error" role="alert">
                {validationError}
              </p>
            )}
          </div>
          <button type="submit" disabled={loading}>
            {loading && <span className="agent-spinner" aria-hidden="true" />}
            {loading ? 'Local AI is working…' : 'Generate AI recommendations'}
          </button>
        </form>
        <aside className="agent-privacy" aria-labelledby="agent-privacy-heading">
          <span className="agent-privacy-lock" aria-hidden="true" />
          <h2 id="agent-privacy-heading">Your profile stays local</h2>
          <p>
            Your profile and request stay within this local application and
            Ollama. No cloud inference or profile storage.
          </p>
          <p>
            Do not include names, contact details, documents, or other sensitive
            information.
          </p>
        </aside>
      </div>
      {loading && (
        <p role="status" className="notice agent-wait-notice">
          The local model is exploring with tools. This can take up to 90
          seconds. You can leave this page to cancel waiting. The local
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
  const resolution = response.name_resolution
  const clarification =
    resolution?.status === 'ambiguous' || resolution?.status === 'not_found'
  const selectedIds = new Set(
    response.recommendations.map((item) => item.assessment.scholarship_id),
  )
  const discovery = response.discovery_candidates ?? []
  const retained = discovery.filter(
    (item) => !selectedIds.has(item.assessment.scholarship_id),
  )
  const displayedIds = new Set([
    ...selectedIds,
    ...discovery.map((item) => item.assessment.scholarship_id),
  ])
  const fallback = (response.fallback_recommendations ?? []).filter(
    (item) => !displayedIds.has(item.assessment.scholarship_id),
  )
  const requestChecks = new Map(
    response.request_matches?.map((item) => [item.scholarship_id, item.checks]),
  )
  const noConfirmedMatches =
    response.status === 'no_matches' &&
    displayedIds.size === 0 &&
    fallback.length === 0 &&
    response.request_preferences?.some((item) => item.mode === 'required')
  const showEmptyModelSelection =
    response.recommendations.length === 0 && !clarification && !noConfirmedMatches
  return (
    <section className="agent-output" aria-label="Local AI response">
      <div className={`notice agent-response agent-response-${response.status}`}>
        <h2>
          {resolution?.status === 'not_found'
            ? 'Programme not found'
            : noConfirmedMatches
              ? 'No confirmed matches'
              : responseHeadings[response.status]}
        </h2>
        <p>{response.message}</p>
        <p>{response.disclaimer}</p>
      </div>
      {resolution?.status === 'ambiguous' && (
        <section
          className="content-panel agent-choices"
          aria-labelledby="programme-choices-heading"
        >
          <h3 id="programme-choices-heading">Matching programmes</h3>
          <p>Enter the full programme name in your request.</p>
          <ul>
            {resolution.options.map((option) => (
              <li key={option.scholarship_id}>
                <strong>{option.scholarship_name}</strong>
                <p>
                  <SourceLink
                    url={option.official_source_url}
                    label={`Official source for ${option.scholarship_name}`}
                  />
                  <span>Last verified {calendarDate(option.last_verified_at)}</span>
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {resolution?.status === 'matched' && resolution.method !== 'exact' && (
        <section
          className="notice agent-interpretation"
          aria-label="Programme-name interpretation"
        >
          <p>{resolution.message}</p>
        </section>
      )}
      {response.warnings.length > 0 && (
        <section className="agent-warnings">
          <h3>Important limitations</h3>
          <ul>
            {response.warnings.map((warning, index) => (
              <li key={`${index}:${warning}`}>
                {warning.replaceAll('needs_verification', 'needs verification')}
              </li>
            ))}
          </ul>
        </section>
      )}
      {response.recommendations.length > 0 && (
        <section
          className="agent-result-group agent-result-group-model"
          aria-labelledby="model-selections-heading"
        >
          <h2 id="model-selections-heading">Model selections</h2>
          <p className="agent-result-context">
            The model selected these programmes. The documented rules determine
            each eligibility assessment.
          </p>
          {response.recommendations.map((item) => (
            <ProgrammeResult
              item={item}
              key={item.assessment.scholarship_id}
              requestChecks={requestChecks.get(item.assessment.scholarship_id)}
              selectedRequirements={response.model_explanations?.find(
                (entry) =>
                  entry.scholarship_id === item.assessment.scholarship_id,
              )?.requirements}
            />
          ))}
        </section>
      )}
      {showEmptyModelSelection && (
        <p className="agent-no-selection">
          No grounded recommendation was returned by the model. Try a simpler
          request or use{' '}
          <a href="#/matches">deterministic matches</a>.
        </p>
      )}
      {retained.length > 0 && (
        <section className="agent-result-group" aria-labelledby="discovery-heading">
          <h2 id="discovery-heading">
            {response.discovery_scope === 'named_target'
              ? 'Requested programme assessments'
              : 'Deterministic discovery candidates'}
          </h2>
          <p className="agent-result-context">
            These candidates are retained by catalogue matching. Review the
            individual assessments and missing evidence below.
          </p>
          {retained.map((item) => (
            <ProgrammeResult
              item={item}
              key={item.assessment.scholarship_id}
              requestChecks={requestChecks.get(item.assessment.scholarship_id)}
            />
          ))}
        </section>
      )}
      {fallback.length > 0 && (
        <section className="agent-result-group" aria-labelledby="fallback-heading">
          <h2 id="fallback-heading">Deterministic candidates to verify</h2>
          <p className="agent-result-context">{response.fallback_reason}</p>
          {fallback.map((item) => (
            <ProgrammeResult
              item={item}
              key={item.assessment.scholarship_id}
              requestChecks={requestChecks.get(item.assessment.scholarship_id)}
            />
          ))}
        </section>
      )}
      <section className="agent-trace content-panel">
        <h2>Tools actually attempted</h2>
        <p className="agent-trace-meta">
          <span>{response.model}</span>
          <span>{response.steps} of 4 model steps</span>
          <span>{response.tool_calls} of 8 tool calls</span>
          <span>Evaluated {calendarDate(response.evaluated_on)} (UTC)</span>
        </p>
        {response.tool_trace.length ? (
          <ol>
            {response.tool_trace.map((item, index) => (
              <li key={index}>
                <div className="agent-trace-step">
                  <h3>Step {item.step}: {item.name.replaceAll('_', ' ')}</h3>
                  <strong
                    className={item.status === 'ok' ? 'trace-success' : undefined}
                  >
                    {item.status === 'ok'
                      ? 'Executed'
                      : item.status.replaceAll('_', ' ')}
                  </strong>
                </div>
                <p>{item.summary}</p>
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

function ProgrammeResult({
  item,
  requestChecks,
  selectedRequirements = [],
}: {
  item: RankedProgramme
  requestChecks?: RequestPreferenceCheck[]
  selectedRequirements?: RequirementResult[]
}) {
  return (
    <article className="agent-programme">
      <Assessment result={item.assessment}>
        {requestChecks && <RequestFit checks={requestChecks} />}
        {selectedRequirements.length > 0 && (
          <section
            className="agent-model-notes"
            aria-label="Model-selected explanation points"
          >
            <h3>Model-selected explanation points</h3>
            <ul>
              {selectedRequirements.map((requirement) => (
                <li key={requirement.requirement}>{requirement.explanation}</li>
              ))}
            </ul>
          </section>
        )}
      </Assessment>
      {item.ranking_reasons.length > 0 && (
        <section className="agent-ranking-notes">
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
        </section>
      )}
    </article>
  )
}

const requestStatus: Record<
  RequestPreferenceCheck['status'],
  { label: string; style: string }
> = {
  confirmed: { label: 'Confirmed', style: 'check-met' },
  unmatched: { label: 'Unmatched', style: 'check-failed' },
  unverified: { label: 'Needs verification', style: 'check-unknown' },
}

function RequestFit({ checks }: { checks: RequestPreferenceCheck[] }) {
  return (
    <section className="agent-request-fit" aria-label="Request fit">
      <h3>Request fit</h3>
      <ul role="list">
        {checks.map((check) => {
          const { label, style } = requestStatus[check.status]
          return (
            <li key={`${check.kind}:${check.mode}:${check.label}`}>
              <div className="agent-request-fit-heading">
                <strong>{check.label}</strong>
                <span className="agent-request-fit-mode">
                  {check.mode === 'required' ? 'Required' : 'Preferred'}{' '}
                  {check.kind}
                </span>
                <span className={`check-label ${style}`}>{label}</span>
              </div>
              <p>{check.evidence}</p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

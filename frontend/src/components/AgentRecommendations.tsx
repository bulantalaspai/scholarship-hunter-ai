import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchAgentRecommendations } from '../agent'
import type { AgentResponse, RequestPreferenceCheck } from '../agent'
import type { RankedProgramme, RequirementResult, StudentProfile } from '../types'
import { calendarDate } from '../display'
import { Assessment, SourceLink } from './ui'

type State =
  | { status: 'idle' | 'loading' | 'stopped' }
  | { status: 'error'; message: string }
  | { status: 'ready'; response: AgentResponse; request: string }

const responseHeadings: Record<AgentResponse['status'], string> = {
  completed: 'Source-backed results',
  needs_verification: 'Further verification needed',
  limit_reached: 'Exploration limit reached',
  no_matches: 'No recommendations selected',
  model_error: 'Local AI could not finish',
  ambiguous_match: 'Choose a programme',
}

const exampleRequests = [
  { label: 'Study in Germany', goal: 'Find scholarships in Germany, including partial funding options.' },
  { label: 'Find full funding', goal: 'Find fully funded scholarships for my profile.' },
  { label: 'Check SMACCs', goal: 'Assess SMACCs for my profile and explain what needs verification.' },
]

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
  const [editingRequest, setEditingRequest] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const goalInput = useRef<HTMLTextAreaElement>(null)
  const resultHeading = useRef<HTMLHeadingElement>(null)

  useEffect(() => () => controller.current?.abort(), [])

  function editGoal(value: string) {
    setGoal(value)
    setValidationError('')
    if (state.status === 'stopped' || state.status === 'error') setState({ status: 'idle' })
  }

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
      if (!pending.signal.aborted) {
        setEditingRequest(false)
        setState({ status: 'ready', response, request: trimmed })
      }
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
  const reading = state.status === 'ready' && !editingRequest
  useEffect(() => {
    if (state.status === 'stopped' || (editingRequest && state.status === 'ready')) goalInput.current?.focus()
    else if (reading) resultHeading.current?.focus()
  }, [editingRequest, reading, state.status])
  return (
    <>
      <div className={reading ? 'page-heading agent-heading agent-heading-report' : 'page-heading agent-heading'}>
        <div>
          <p className="breadcrumb">
            <a href="#/profile">My profile</a> / Local AI
          </p>
          <h1>Local AI recommendations</h1>
          {!reading && (
            <p>
              Explore scholarships with your profile. Eligibility follows the documented programme rules.
            </p>
          )}
        </div>
        <a className="agent-matches-link" href="#/matches">
          Use deterministic matches
        </a>
      </div>
      {reading && (
        <div className="agent-request-receipt">
          <div><strong>Your request</strong><p>{state.request}</p></div>
          <button type="button" className="button-secondary"
            aria-controls="agent-request-editor" onClick={() => setEditingRequest(true)}>
            Edit request
          </button>
        </div>
      )}
      <div className="agent-workspace" id="agent-request-editor" hidden={reading}>
        <div className="agent-composer">
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
                onChange={(event) => editGoal(event.target.value)}
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
              <div className="agent-input-meta">
                <small id="agent-goal-hint">Name a destination, funding preference or programme.<span className="sr-only"> Up to 300 characters.</span></small>
                <span aria-hidden="true">{goal.length} / 300</span>
              </div>
              {validationError && (
                <p className="field-error" id="agent-goal-error" role="alert">
                  {validationError}
                </p>
              )}
            </div>
            <div className="agent-editor-actions">
              <button type="submit" disabled={loading}>
                {loading && <span className="agent-spinner" aria-hidden="true" />}
                {loading ? 'Local AI is working…' : 'Generate AI recommendations'}
                {!loading && <span aria-hidden="true">→</span>}
              </button>
              {editingRequest && state.status === 'ready' && (
                <button type="button" className="button-text" onClick={() => {
                  setGoal(state.request)
                  setValidationError('')
                  setEditingRequest(false)
                }}>
                  Back to results
                </button>
              )}
            </div>
          </form>
          {loading && (
            <div className="agent-wait-notice">
              <p role="status"><strong>Waiting for the local model</strong>
                This can take up to 90 seconds. If you stop waiting, processing may continue locally.
              </p>
              <button className="button-text" type="button" onClick={() => {
                controller.current?.abort()
                setState({ status: 'stopped' })
              }}>Stop waiting</button>
            </div>
          )}
          {state.status === 'stopped' && <p role="status" className="agent-stopped">You stopped waiting. Your request is ready to edit or send again.</p>}
          <details className="agent-privacy">
            <summary>Your profile stays local</summary>
            <p>Your profile stays in memory. This application sends your request to local Ollama. Leave out names, contact details, documents and other sensitive information.</p>
          </details>
        </div>
        <aside className="agent-examples" aria-labelledby="agent-examples-heading">
          <h2 id="agent-examples-heading">Try an example</h2>
          <p>You can edit each example before sending.</p>
          {exampleRequests.map((example) => (
            <button key={example.label} type="button" disabled={loading}
              aria-controls="agent-goal"
              onClick={() => {
                editGoal(example.goal)
                goalInput.current?.focus()
              }}>
              {example.label}<span aria-hidden="true">↖</span>
            </button>
          ))}
        </aside>
      </div>
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
      {state.status === 'ready' && !editingRequest && (
        <AgentOutput response={state.response} headingRef={resultHeading} />
      )}
    </>
  )
}

function AgentOutput({
  response,
  headingRef,
}: {
  response: AgentResponse
  headingRef: React.Ref<HTMLHeadingElement>
}) {
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
  const disclaimers = [...new Set([
    response.disclaimer,
    ...[...response.recommendations, ...retained, ...fallback].map(
      (item) => item.assessment.disclaimer,
    ),
  ])]
  const noConfirmedMatches =
    response.status === 'no_matches' &&
    displayedIds.size === 0 &&
    fallback.length === 0 &&
    response.request_preferences?.some((item) => item.mode === 'required')
  const showEmptyModelSelection =
    response.recommendations.length === 0 && !clarification && !noConfirmedMatches
  return (
    <section className="agent-output" aria-label="Local AI response">
      <div className="agent-report-notes">
        <div className={`notice agent-response agent-response-${response.status}`}>
          <h2 ref={headingRef} tabIndex={-1}>
            {resolution?.status === 'not_found'
              ? 'Programme not found'
              : noConfirmedMatches
                ? 'No confirmed matches'
                : responseHeadings[response.status]}
          </h2>
          <p>{response.message}</p>
        </div>
        {resolution?.status === 'matched' && resolution.method !== 'exact' && (
          <section
            className="notice agent-interpretation"
            aria-label="Programme-name interpretation"
          >
            <p>{resolution.message}</p>
          </section>
        )}
        <section className="agent-warnings">
          <h3>Important limitations</h3>
          {disclaimers.map((text) => <p className="agent-disclaimer" key={text}>{text}</p>)}
          {response.warnings.length > 0 && (
            <ul>
              {response.warnings.map((warning, index) => (
                <li key={`${index}:${warning}`}>
                  {warning.replaceAll('needs_verification', 'needs verification')}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <div className="agent-report-programmes">
        {resolution?.status === 'ambiguous' && (
          <section className="agent-choices" aria-labelledby="programme-choices-heading">
            <h2 id="programme-choices-heading">Matching programmes</h2>
            <p>Enter the full programme name in your request.</p>
            <ul>
              {resolution.options.map((option) => (
                <li key={option.scholarship_id}>
                  <strong>{option.scholarship_name}</strong>
                  <p>
                    <SourceLink url={option.official_source_url} label={`Official source for ${option.scholarship_name}`} />
                    <span>Last verified {calendarDate(option.last_verified_at)}</span>
                  </p>
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
              Eligibility checked against documented rules.
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
              {fallback.length === 0 && response.fallback_recommendations?.length
                ? response.fallback_reason
                : 'Catalogue matching retained these programmes for a deterministic assessment.'}
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
      </div>
      <section className="agent-trace">
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
  const details = (
    <>
      {requestChecks && requestChecks.length > 0 && (
        <section className="agent-fit-evidence" aria-label="Request evidence">
          <h3>Request evidence</h3>
          <ul>
            {requestChecks.map((check) => (
              <li key={`${check.kind}:${check.mode}:${check.label}`}>
                <strong>{check.label}</strong> · {check.evidence}
              </li>
            ))}
          </ul>
        </section>
      )}
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
    </>
  )
  return (
    <article className="agent-programme">
      <Assessment result={item.assessment} agentSummary details={details}>
        {requestChecks && <RequestFit checks={requestChecks} />}
      </Assessment>
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
            </li>
          )
        })}
      </ul>
    </section>
  )
}

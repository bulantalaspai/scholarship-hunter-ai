import type {
  EligibilityResult,
  EligibilityStatus,
  Scholarship,
} from '../types'
import { calendarDate, fundingLabels, statusLabels } from '../display'
import ProgrammeFacts from './ProgrammeFacts'

export function StatusBadge({ status }: { status: EligibilityStatus }) {
  return (
    <span className={`badge status-${status}`}>{statusLabels[status]}</span>
  )
}

export function SourceLink({
  url,
  label = 'View official source',
}: {
  url: string
  label?: string
}) {
  // API responses are validated as HTTPS; keep this final rendering boundary safe too.
  let valid = false
  try {
    const parsed = new URL(url)
    valid = parsed.protocol === 'https:' && !parsed.username && !parsed.password
  } catch {
    /* Invalid source URLs are never rendered as links. */
  }
  if (!valid) return <span>Source link unavailable</span>
  return (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {label}
      <span className="sr-only"> (opens in a new tab)</span>{' '}
      <span aria-hidden="true">↗</span>
    </a>
  )
}

export function ErrorState({
  message,
  retry,
}: {
  message: string
  retry: () => void
}) {
  return (
    <section className="state-panel error-panel" role="alert">
      <h2>We couldn’t load this information</h2>
      <p>{message}</p>
      <button type="button" onClick={retry}>
        Try again
      </button>
    </section>
  )
}

export function LoadingState({
  children = 'Loading scholarships…',
}: {
  children?: string
}) {
  return (
    <div className="state-panel loading-panel" role="status">
      <span className="loading-mark" aria-hidden="true" />
      {children}
    </div>
  )
}

export function EmptyState({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="state-panel">
      <span className="empty-mark" aria-hidden="true" />
      <h2>{title}</h2>
      {children}
    </section>
  )
}

export function ScholarshipCard({ scholarship }: { scholarship: Scholarship }) {
  const details = `#/scholarships/${scholarship.id}`
  return (
    <article className="scholarship-card">
      <div className="directory-programme">
        <p className="directory-provider">
          {scholarship.university_or_provider}
          <span>{scholarship.degree_level ?? 'Degree level not confirmed'}</span>
        </p>
        <h2>
          <a href={details}>{scholarship.scholarship_name}</a>
        </h2>
        <p className="directory-fields">
          {scholarship.eligible_study_fields?.join(', ') ||
            'Study fields need verification'}
        </p>
      </div>
      <div className="directory-award">
        <span className={`badge funding-${scholarship.funding_type}`}>
          {fundingLabels[scholarship.funding_type]}
        </span>
        <p className="directory-destination">
          <span className="destination-mark" aria-hidden="true" />
          <span>
            {scholarship.destination_country?.join(', ') ||
              'Destination not confirmed'}
          </span>
        </p>
      </div>
      <div className="directory-evidence">
        <dl>
          <div>
            <dt>Deadline</dt>
            <dd>
              {scholarship.application_deadline ? (
                <time dateTime={scholarship.application_deadline}>
                  {calendarDate(scholarship.application_deadline)}
                </time>
              ) : (
                calendarDate(null)
              )}
            </dd>
          </div>
          <div>
            <dt>Last verified</dt>
            <dd>
              <time dateTime={scholarship.last_verified_at}>
                {calendarDate(scholarship.last_verified_at)}
              </time>
            </dd>
          </div>
        </dl>
        <SourceLink url={scholarship.official_source_url} />
      </div>
      <a
        className="directory-open"
        aria-label="View scholarship"
        title={scholarship.scholarship_name}
        href={details}
      >
        <span aria-hidden="true">→</span>
      </a>
    </article>
  )
}

export function Assessment({
  result,
  children,
  details,
  agentSummary = false,
}: {
  result: EligibilityResult
  children?: React.ReactNode
  details?: React.ReactNode
  agentSummary?: boolean
}) {
  const checks = [
    { count: result.matched_requirements.length, label: 'met', style: 'met' },
    { count: result.failed_requirements.length, label: 'failed', style: 'failed' },
    { count: result.unknown_requirements.length, label: 'unknown', style: 'unknown' },
  ]
  const scopeChecks = (
    <div className="scope-grid">
      {(['admission', 'funding', 'application'] as const).map((scope) => (
        <div className="scope-result" key={scope}>
          <h3>
            {scope === 'application'
              ? 'Application availability'
              : `${scope[0].toUpperCase()}${scope.slice(1)} eligibility`}
          </h3>
          <StatusBadge status={result[`${scope}_status`]} />
        </div>
      ))}
    </div>
  )
  const Heading = agentSummary ? 'h3' : 'h2'
  return (
    <section className={`assessment assessment-${result.status}`} aria-label="Eligibility assessment">
      <header className="assessment-intro">
        <Heading>{result.scholarship_name}</Heading>
        <StatusBadge status={result.status} />
      </header>
      <div className="assessment-reference">
        {agentSummary && <ProgrammeFacts assessment={result} />}
        <p className="assessment-source">
          <SourceLink url={result.official_source_url} />
          <span>Last verified {calendarDate(result.last_verified_at)}</span>
        </p>
      </div>
      {!agentSummary && scopeChecks}
      {result.failed_requirements.length > 0 && (
        <p className="assessment-failures">
          <strong>Unmet requirements</strong>{' '}
          {result.failed_requirements.map((key) => key.replaceAll('_', ' ')).join(', ')}
        </p>
      )}
      {children}
      {!agentSummary && <p className="assessment-disclaimer">{result.disclaimer}</p>}
      <details className="assessment-disclosure">
        <summary>
          <strong>Assessment details</strong>
          <span className="assessment-tally">
            {checks.map((item) => (
              <span className={`count-${item.style}`} key={item.style}>
                {item.count} {item.label}
              </span>
            ))}
          </span>
        </summary>
        <div className="assessment-details">
          {agentSummary && scopeChecks}
          <p className="assessment-explanation">{result.explanation}</p>
          {details}
          <div className="assessment-checks">
            <h3>Requirement checks</h3>
            <ul className="requirement-list">
              {result.requirements.map((item) => (
                <li key={item.requirement}>
                  <div className="requirement-heading">
                    <h4>{item.requirement === 'gpa' ? 'GPA' : item.requirement.replaceAll('_', ' ')}</h4>
                    <span className={`check-label check-${item.status}`}>
                      {item.status === 'met' ? 'Met' : item.status === 'failed' ? 'Not met' : 'Needs verification'}
                    </span>
                  </div>
                  <div>
                    <p>{item.explanation}</p>
                    {item.suggestion && <p className="suggestion">Next step: {item.suggestion}</p>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
          {result.unknown_requirements.length > 0 && (
            <div className="assessment-unknowns">
              <h3>Information still to verify</h3>
              <p>{result.unknown_requirements.map((name) => name.replaceAll('_', ' ')).join(', ')}.</p>
            </div>
          )}
          {result.suggestions.length > 0 && (
            <section className="assessment-next-steps">
              <h3>Suggested next steps</h3>
              <ul>{result.suggestions.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          )}
          <section className="assessment-evidence">
            <h3>Evidence behind this check</h3>
            <p>Assessed on {calendarDate(result.evaluated_on)} (UTC).</p>
            <p>Structured rules {result.rules_verified_at ? `reviewed ${calendarDate(result.rules_verified_at)}` : 'not confirmed for this record'}.</p>
            {result.rule_source_urls.length > 0 && (
              <ul>{result.rule_source_urls.map((url, index) => (
                <li key={url}><SourceLink url={url} label={`Rule evidence ${index + 1}`} /></li>
              ))}</ul>
            )}
          </section>
        </div>
      </details>
    </section>
  )
}

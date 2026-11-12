import type {
  EligibilityResult,
  EligibilityStatus,
  Scholarship,
} from '../types'
import { calendarDate, fundingLabels, statusLabels } from '../display'

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
      <div className="empty-mark" aria-hidden="true">
        ⌕
      </div>
      <h2>{title}</h2>
      {children}
    </section>
  )
}

export function ScholarshipCard({ scholarship }: { scholarship: Scholarship }) {
  return (
    <article className="scholarship-card">
      <div className="card-top">
        <span className="provider-mark" aria-hidden="true">
          {scholarship.university_or_provider.slice(0, 2).toUpperCase()}
        </span>
        <span>{scholarship.university_or_provider}</span>
        <span className={`badge funding-${scholarship.funding_type}`}>
          {fundingLabels[scholarship.funding_type]}
        </span>
      </div>
      <h2>
        <a href={`#/scholarships/${scholarship.id}`}>
          {scholarship.scholarship_name}
        </a>
      </h2>
      <p className="card-destination">
        {scholarship.destination_country?.join(' · ') ??
          'Destination not confirmed'}{' '}
        <span className="separator">/</span>{' '}
        {scholarship.degree_level ?? 'Degree level not confirmed'}
      </p>
      <p className="field-tags">
        {scholarship.eligible_study_fields?.join(', ') ??
          'Study fields need verification'}
      </p>
      <dl className="card-facts">
        <div>
          <dt>Application deadline</dt>
          <dd>{calendarDate(scholarship.application_deadline)}</dd>
        </div>
        <div>
          <dt>Last verified</dt>
          <dd>{calendarDate(scholarship.last_verified_at)}</dd>
        </div>
      </dl>
      <div className="card-actions">
        <a
          className="button button-secondary"
          href={`#/scholarships/${scholarship.id}`}
        >
          View scholarship
        </a>
        <SourceLink url={scholarship.official_source_url} />
      </div>
    </article>
  )
}

export function Assessment({ result }: { result: EligibilityResult }) {
  return (
    <section className="assessment" aria-label="Eligibility assessment">
      <div className="assessment-intro">
        <StatusBadge status={result.status} />
        <h2>{result.scholarship_name}</h2>
        <p>{result.explanation}</p>
      </div>
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
      <p className="notice">{result.disclaimer}</p>
      <h3>Requirement checks</h3>
      <ul className="requirement-list">
        {result.requirements.map((item) => (
          <li key={item.requirement}>
            <span
              className={`check-symbol check-${item.status}`}
              aria-hidden="true"
            >
              {item.status === 'met'
                ? '✓'
                : item.status === 'failed'
                  ? '×'
                  : '?'}
            </span>
            <div>
              <div className="requirement-heading">
                <h4>{item.requirement.replaceAll('_', ' ')}</h4>
                <span className={`check-label check-${item.status}`}>
                  {item.status === 'met'
                    ? 'Met'
                    : item.status === 'failed'
                      ? 'Not met'
                      : 'Needs verification'}
                </span>
              </div>
              <p>{item.explanation}</p>
              {item.suggestion && (
                <p className="suggestion">Next step: {item.suggestion}</p>
              )}
            </div>
          </li>
        ))}
      </ul>
      {result.unknown_requirements.length > 0 && (
        <div className="notice">
          <h3>Information still to verify</h3>
          <p>
            {result.unknown_requirements
              .map((name) => name.replaceAll('_', ' '))
              .join(', ')}
            .
          </p>
        </div>
      )}
      {result.suggestions.length > 0 && (
        <section>
          <h3>Suggested next steps</h3>
          <ul>
            {result.suggestions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}
      <div className="evidence-panel">
        <h3>Evidence behind this check</h3>
        <p>
          <SourceLink url={result.official_source_url} /> · Last verified{' '}
          {calendarDate(result.last_verified_at)}
        </p>
        <p>
          Assessed on {calendarDate(result.evaluated_on)} (UTC). Structured
          rules:{' '}
          {result.rules_verified_at
            ? `reviewed ${calendarDate(result.rules_verified_at)}`
            : 'not confirmed for this record'}
          .
        </p>
        {result.rule_source_urls.length > 0 && (
          <ul>
            {result.rule_source_urls.map((url, index) => (
              <li key={url}>
                <SourceLink url={url} label={`Rule evidence ${index + 1}`} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

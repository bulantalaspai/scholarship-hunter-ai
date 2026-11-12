import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import {
  checkEligibility,
  getMatches,
  getScholarship,
  listScholarships,
} from './api'
import { useResource } from './hooks'
import type { FundingType, ScholarshipPage, StudentProfile } from './types'
import ConnectionCheck from './components/ConnectionCheck'
import { calendarDate, fundingLabels, statusLabels } from './display'
import {
  Assessment,
  EmptyState,
  ErrorState,
  LoadingState,
  ScholarshipCard,
  SourceLink,
  StatusBadge,
} from './components/ui'

export function Home() {
  const [field, setField] = useState('')
  return (
    <>
      <ConnectionCheck />
      <section className="home-hero">
        <div className="hero-copy">
          <h1>Scholarship Hunter AI</h1>
          <p className="hero-title">A clearer path to a funded master’s.</p>
          <p className="hero-description">
            Discover opportunities abroad. Understand the requirements. Take
            your next step with evidence you can check.
          </p>
          <form
            className="home-search"
            onSubmit={(event) => {
              event.preventDefault()
              window.location.hash = `/explore?${new URLSearchParams(field.trim() ? { field: field.trim() } : {})}`
            }}
          >
            <label htmlFor="home-field">What would you like to study?</label>
            <div>
              <input
                id="home-field"
                value={field}
                onChange={(event) => setField(event.target.value)}
                maxLength={100}
                placeholder="e.g. Engineering"
              />
              <button type="submit">Explore scholarships</button>
            </div>
          </form>
          <a className="text-link" href="#/profile">
            Or start with your student profile <span aria-hidden="true">↗</span>
          </a>
        </div>
        <aside className="journey-panel" aria-label="How it works">
          <div className="orbital-mark" aria-hidden="true">
            <svg viewBox="0 0 240 180">
              <ellipse cx="120" cy="90" rx="100" ry="60" />
              <ellipse
                cx="120"
                cy="90"
                rx="45"
                ry="85"
                transform="rotate(40 120 90)"
              />
              <path d="M20 90h200M120 10v160" />
              <circle cx="120" cy="90" r="16" />
              <circle cx="193" cy="48" r="8" />
            </svg>
          </div>
          <h2>
            Your next chapter,
            <br />
            with a clearer direction.
          </h2>
          <ol className="journey-steps">
            <li>
              <strong>Discover</strong>
              <span>Browse a curated, source-linked catalogue.</span>
            </li>
            <li>
              <strong>Understand</strong>
              <span>Compare your profile with documented rules.</span>
            </li>
            <li>
              <strong>Decide</strong>
              <span>See what matches and what still needs checking.</span>
            </li>
          </ol>
        </aside>
      </section>
      <section className="trust-section" aria-label="Our approach">
        <div>
          <h2>Official sources, always in view.</h2>
          <p>
            Every record links back to its provider and shows a verification
            date.
          </p>
        </div>
        <div>
          <h2>Uncertainty stays visible.</h2>
          <p>
            A missing requirement is a reason to check, never an automatic yes.
          </p>
        </div>
        <div>
          <h2>Your profile stays yours.</h2>
          <p>
            No account. No saved profile. Comparisons use the local application.
          </p>
        </div>
      </section>
    </>
  )
}

export function Pagination({
  page,
  total,
  pageSize = 10,
  link,
}: {
  page: number
  total: number
  pageSize?: number
  link: (page: number) => string
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <nav className="pagination" aria-label="Results pages">
      {page > pages ? (
        <a className="button button-secondary" href={link(1)}>
          First page
        </a>
      ) : page > 1 ? (
        <a className="button button-secondary" href={link(page - 1)}>
          Previous page
        </a>
      ) : (
        <span />
      )}
      <span>
        {page > pages
          ? `Page ${page} is outside the available results`
          : `Page ${page} of ${pages}`}
      </span>
      {page < pages ? (
        <a className="button button-secondary" href={link(page + 1)}>
          Next page
        </a>
      ) : (
        <span />
      )}
    </nav>
  )
}

export function Explorer({ query }: { query: string }) {
  const params = new URLSearchParams(query)
  const country = params.get('country') ?? ''
  const field = params.get('field') ?? ''
  const funding = params.get('funding_type') ?? ''
  const page = Number(params.get('page') ?? 1)
  const invalid =
    country.trim().length > 100 ||
    field.trim().length > 100 ||
    !Number.isInteger(page) ||
    page < 1 ||
    page > 1_000_000 ||
    !['', 'fully_funded', 'partially_funded', 'unknown'].includes(funding)
  const [draft, setDraft] = useState({ country, field, funding })
  const loader = useCallback(
    (signal: AbortSignal) =>
      listScholarships(
        {
          country: country.trim() || undefined,
          field: field.trim() || undefined,
          funding_type: (funding || undefined) as FundingType | undefined,
          page,
          page_size: 10,
        },
        signal,
      ),
    [country, field, funding, page],
  )
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="breadcrumb">
            <a href="#/">Home</a> / Explorer
          </p>
          <h1>Scholarship explorer</h1>
          <p>Find opportunities that deserve a closer look.</p>
        </div>
        <a className="button button-secondary" href="#/profile">
          Find my matches
        </a>
      </div>
      <div className="explorer-layout">
        <aside className="filter-panel">
          <h2>Refine your search</h2>
          <form
            onSubmit={(event: FormEvent) => {
              event.preventDefault()
              const search = new URLSearchParams()
              if (draft.country.trim())
                search.set('country', draft.country.trim())
              if (draft.field.trim()) search.set('field', draft.field.trim())
              if (draft.funding) search.set('funding_type', draft.funding)
              window.location.hash = `/explore?${search}`
            }}
          >
            <div className="field">
              <label htmlFor="filter-country">Destination country</label>
              <input
                id="filter-country"
                value={draft.country}
                onChange={(event) =>
                  setDraft({ ...draft, country: event.target.value })
                }
                maxLength={100}
                placeholder="e.g. Germany"
              />
              <small>Matches a full country name.</small>
            </div>
            <div className="field">
              <label htmlFor="filter-field">Study field</label>
              <input
                id="filter-field"
                value={draft.field}
                onChange={(event) =>
                  setDraft({ ...draft, field: event.target.value })
                }
                maxLength={100}
                placeholder="e.g. Computer Science"
              />
              <small>Searches documented study fields.</small>
            </div>
            <div className="field">
              <label htmlFor="filter-funding">Funding type</label>
              <select
                id="filter-funding"
                value={draft.funding}
                onChange={(event) =>
                  setDraft({ ...draft, funding: event.target.value })
                }
              >
                <option value="">All funding types</option>
                <option value="fully_funded">Fully funded</option>
                <option value="partially_funded">Partially funded</option>
                <option value="unknown">Not confirmed</option>
              </select>
            </div>
            <button type="submit">Apply filters</button>
            <a className="reset-link" href="#/explore">
              Clear filters
            </a>
          </form>
          <p className="filter-note">
            A filter match is a starting point, not an eligibility decision.
          </p>
        </aside>
        <section aria-label="Scholarship results">
          {invalid ? (
            <ErrorState
              message="This search link contains an invalid filter or page. Clear the filters to start again."
              retry={() => {
                window.location.hash = '/explore'
              }}
            />
          ) : (
            <ExplorerResults query={query} loader={loader} page={page} />
          )}
        </section>
      </div>
    </>
  )
}

function ExplorerResults({
  query,
  loader,
  page,
}: {
  query: string
  loader: (signal: AbortSignal) => Promise<ScholarshipPage>
  page: number
}) {
  const { resource, retry } = useResource(query, loader)
  if (resource.status === 'loading') return <LoadingState />
  if (resource.status === 'error')
    return <ErrorState message={resource.message} retry={retry} />
  const result = resource.data
  const pageLink = (next: number) => {
    const params = new URLSearchParams(query)
    params.set('page', String(next))
    return `#/explore?${params}`
  }
  return (
    <>
      <div className="results-heading">
        <p aria-live="polite">
          <strong>{result.total}</strong>{' '}
          {result.total === 1 ? 'opportunity' : 'opportunities'} in this search
        </p>
        <span className="muted">Curated catalogue</span>
      </div>
      <p className="catalogue-note">
        Funding and requirements can change. Recheck the official source before
        applying.
      </p>
      {result.items.length ? (
        <div className="card-list">
          {result.items.map((item) => (
            <ScholarshipCard key={item.id} scholarship={item} />
          ))}
        </div>
      ) : (
        <EmptyState
          title={
            result.total
              ? 'No opportunities on this page'
              : 'No scholarships found'
          }
        >
          <p>
            {result.total
              ? 'Use the page controls to return to the available results.'
              : 'Try a broader study field, a different destination, or clear your filters. Missing catalogue data may also exclude a record from a filtered search.'}
          </p>
          <a href="#/explore" className="button button-secondary">
            Browse the full catalogue
          </a>
        </EmptyState>
      )}
      {result.total > 0 && (
        <Pagination page={page} total={result.total} link={pageLink} />
      )}
    </>
  )
}

export function ScholarshipDetails({ id }: { id: number }) {
  const loader = useCallback(
    (signal: AbortSignal) => getScholarship(id, signal),
    [id],
  )
  const { resource, retry } = useResource(String(id), loader)
  if (resource.status === 'loading')
    return <LoadingState>Loading scholarship details…</LoadingState>
  if (resource.status === 'error')
    return (
      <>
        <a href="#/explore">Back to explorer</a>
        <ErrorState message={resource.message} retry={retry} />
      </>
    )
  const item = resource.data
  const facts: [string, string | null][] = [
    ['Destination', item.destination_country?.join(', ') ?? null],
    ['Awarded degree', item.degree_level],
    ['Study fields', item.eligible_study_fields?.join(', ') ?? null],
    ['Nationality scope', item.eligible_nationalities?.join(', ') ?? null],
    [
      'Minimum GPA',
      item.minimum_gpa !== null
        ? `${item.minimum_gpa} / ${item.gpa_scale ?? 'scale unconfirmed'}`
        : null,
    ],
    [
      'IELTS overall',
      item.minimum_ielts !== null
        ? `${item.minimum_ielts} — check language alternatives and component conditions below`
        : null,
    ],
    ['Application cycle', item.application_cycle],
    [
      'Application deadline',
      item.application_deadline
        ? calendarDate(item.application_deadline)
        : null,
    ],
  ]
  return (
    <>
      <p className="breadcrumb">
        <a href="#/explore">Scholarship explorer</a> / Details
      </p>
      <div className="detail-heading">
        <span className={`badge funding-${item.funding_type}`}>
          {fundingLabels[item.funding_type]}
        </span>
        <h1>{item.scholarship_name}</h1>
        <p>{item.university_or_provider}</p>
        <div className="action-row">
          <a className="button" href={`#/profile?scholarship=${id}`}>
            Check my eligibility
          </a>
          <SourceLink url={item.official_source_url} />
        </div>
      </div>
      <div className="details-layout">
        <div>
          <section className="content-panel">
            <h2>At a glance</h2>
            <dl className="detail-facts">
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>
                    {value ?? (
                      <span className="unknown-value">
                        Not confirmed — verify with the provider
                      </span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="content-panel">
            <h2>Funding and coverage</h2>
            <h3>Tuition</h3>
            <p>
              {item.tuition_coverage ?? 'Tuition coverage is not confirmed.'}
            </p>
            <h3>Living support</h3>
            <p>{item.living_stipend ?? 'Living support is not confirmed.'}</p>
            <p className="notice">
              Published funding terms describe the opportunity. Receiving an
              award remains subject to selection.
            </p>
          </section>
          <section className="content-panel">
            <h2>Requirements and important notes</h2>
            <p className="preserve-lines">
              {item.additional_requirements ??
                'Additional requirements have not been confirmed.'}
            </p>
            <p className="preserve-lines">
              {item.notes ?? 'No additional source notes have been recorded.'}
            </p>
          </section>
        </div>
        <aside className="detail-sidebar">
          <section className="evidence-panel">
            <h2>Check the evidence</h2>
            <p>
              Last verified
              <br />
              <strong>{calendarDate(item.last_verified_at)}</strong>
            </p>
            <SourceLink url={item.official_source_url} />
            <p>
              A verification date is a snapshot, not proof that applications are
              currently open.
            </p>
          </section>
          <p className="notice">
            “Not confirmed” does not mean a requirement is waived. Use the
            eligibility check to see which conditions need review.
          </p>
        </aside>
      </div>
    </>
  )
}

export function EligibilityPage({
  id,
  profile,
}: {
  id: number
  profile: StudentProfile
}) {
  const loader = useCallback(
    (signal: AbortSignal) => checkEligibility(id, profile, signal),
    [id, profile],
  )
  const { resource, retry } = useResource(
    `${id}:${JSON.stringify(profile)}`,
    loader,
  )
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="breadcrumb">
            <a href={`#/scholarships/${id}`}>Scholarship details</a> /
            Eligibility
          </p>
          <h1>Your eligibility check</h1>
          <p>A transparent comparison with documented requirements.</p>
        </div>
        <a
          className="button button-secondary"
          href={`#/profile?scholarship=${id}`}
        >
          Edit profile
        </a>
      </div>
      {resource.status === 'loading' ? (
        <LoadingState>Checking documented requirements…</LoadingState>
      ) : resource.status === 'error' ? (
        <ErrorState message={resource.message} retry={retry} />
      ) : (
        <Assessment result={resource.data} />
      )}
    </>
  )
}

export function MatchesPage({
  profile,
  page,
}: {
  profile: StudentProfile
  page: number
}) {
  const loader = useCallback(
    (signal: AbortSignal) => getMatches(profile, page, signal),
    [profile, page],
  )
  const { resource, retry } = useResource(
    `${page}:${JSON.stringify(profile)}`,
    loader,
  )
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="breadcrumb">
            <a href="#/profile">My profile</a> / Matches
          </p>
          <h1>Your scholarship matches</h1>
          <p>Clear groups. Explainable criteria. No guessed probabilities.</p>
        </div>
        <a className="button button-secondary" href="#/profile">
          Edit profile
        </a>
      </div>
      {resource.status === 'loading' ? (
        <LoadingState>Comparing your profile with the catalogue…</LoadingState>
      ) : resource.status === 'error' ? (
        <ErrorState message={resource.message} retry={retry} />
      ) : (
        <>
          <div className="match-summary">
            {(['eligible', 'needs_verification', 'ineligible'] as const).map(
              (status) => (
                <div key={status}>
                  <span>{statusLabels[status]}</span>
                  <strong>{resource.data.counts[status]}</strong>
                </div>
              ),
            )}
          </div>
          <p className="notice">
            An eligibility assessment does not guarantee admission or funding.
            Unknown conditions stay unverified. Groups are ranked by
            eligibility, published funding type, and exact field relevance.
          </p>
          {resource.data.counts.eligible === 0 && resource.data.total > 0 && (
            <p className="catalogue-note">
              No fully verified eligible programmes were found. Review
              unresolved conditions and confirmed failures below.
            </p>
          )}
          {resource.data.total === 0 && (
            <EmptyState title="No opportunities to compare yet">
              <p>
                The local catalogue is empty. Return to the explorer after
                scholarship records have been imported.
              </p>
              <a href="#/explore">Open explorer</a>
            </EmptyState>
          )}
          {resource.data.total > 0 &&
            resource.data.eligible.length +
              resource.data.needs_verification.length +
              resource.data.ineligible.length ===
              0 && (
              <EmptyState title="No matches on this page">
                <p>Your comparison has results on another page.</p>
                <a href="#/matches?page=1">Return to the first page</a>
              </EmptyState>
            )}
          {(['eligible', 'needs_verification', 'ineligible'] as const).map(
            (status) =>
              resource.data[status].length > 0 && (
                <section className="match-group" key={status}>
                  <h2>
                    {statusLabels[status]}{' '}
                    <span className="muted">
                      ({resource.data.counts[status]})
                    </span>
                  </h2>
                  {resource.data[status].map((item) => (
                    <article
                      className="match-card"
                      key={item.assessment.scholarship_id}
                    >
                      <StatusBadge status={item.assessment.status} />
                      <h3>
                        <a href={`#/results/${item.assessment.scholarship_id}`}>
                          {item.assessment.scholarship_name}
                        </a>
                      </h3>
                      <p>{item.assessment.explanation}</p>
                      <ul className="ranking-reasons">
                        {item.ranking_reasons.map((reason) => (
                          <li key={reason}>
                            {reason
                              .replaceAll(
                                'needs_verification',
                                'needs verification',
                              )
                              .replaceAll('fully_funded', 'fully funded')
                              .replaceAll(
                                'partially_funded',
                                'partially funded',
                              )}
                          </li>
                        ))}
                      </ul>
                      <div className="card-actions">
                        <a
                          className="button button-secondary"
                          href={`#/results/${item.assessment.scholarship_id}`}
                        >
                          View requirement checks
                        </a>
                        <SourceLink url={item.assessment.official_source_url} />
                      </div>
                    </article>
                  ))}
                </section>
              ),
          )}
          {resource.data.total > 0 && (
            <Pagination
              page={page}
              total={resource.data.total}
              link={(next) => `#/matches?page=${next}`}
            />
          )}
        </>
      )}
    </>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { calendarDate } from '../display'
import { useResource } from '../hooks'
import {
  auditDate, decisionLabels, fieldLabel, loadReviewDraft, loadReviewQueue,
  requiredFields, ReviewRequestError, submitReview, valueLabel,
} from '../review'
import type { ReviewDetail, ReviewSummary } from '../review'
import ReviewEvidence, { StipendEvidence } from './ReviewEvidence'
import { ErrorState, LoadingState, SourceLink } from './ui'
import '../review.css'

const stateLabels = {
  pending_review: 'Pending review',
  needs_more_evidence: 'Needs evidence',
  approved: 'Approved',
  rejected: 'Rejected',
}

function heading(draft: ReviewSummary) {
  return draft.candidate_label || draft.scholarship_name || 'Unnamed draft'
}

function sourceHost(source: string) {
  try {
    return new URL(source).hostname.replace(/^www\./, '')
  } catch {
    return 'Source unavailable'
  }
}

function StateBadge({ draft }: { draft: ReviewSummary }) {
  const approved = draft.state === 'approved'
  const appearance = approved ? 'review-success' : draft.state === 'rejected' ? 'review-danger' : 'review-warning'
  return <span className={'badge review-badge ' + appearance}>
    {draft.published_id === null ? stateLabels[draft.state] : 'Published'}
  </span>
}

function errorMessage(error: unknown) {
  return error instanceof ReviewRequestError ? error.message : 'The review operation could not be completed.'
}

export default function ReviewDashboard() {
  const [session, setSession] = useState<{ accessKey: string; queue: ReviewSummary[] }>()
  const [keyInput, setKeyInput] = useState('')
  const [feedback, setFeedback] = useState('')
  const pending = useRef<AbortController | null>(null)
  const [unlocking, setUnlocking] = useState(false)
  const keyField = useRef<HTMLInputElement>(null)
  const pageTitle = useRef<HTMLHeadingElement>(null)
  const lock = useCallback(() => {
    setSession(undefined)
    setFeedback('')
    setKeyInput('')
  }, [])

  useEffect(() => () => pending.current?.abort(), [])
  useEffect(() => {
    if (session) pageTitle.current?.focus()
    else keyField.current?.focus()
  }, [session])

  async function unlock(event: FormEvent) {
    event.preventDefault()
    const accessKey = keyInput.trim()
    if (!accessKey || pending.current) return
    setUnlocking(true)
    setFeedback('')
    const request = new AbortController()
    pending.current = request
    try {
      const queue = await loadReviewQueue(accessKey, request.signal)
      if (!request.signal.aborted) {
        setSession({ accessKey, queue })
        setKeyInput('')
      }
    } catch (error) {
      if (!request.signal.aborted) setFeedback(errorMessage(error))
    } finally {
      pending.current = null
      if (!request.signal.aborted) setUnlocking(false)
    }
  }

  return <div className="review-page">
    <header className="review-header">
      <div>
        <h1 ref={pageTitle} tabIndex={-1}>Scholarship review</h1>
        <p>Inspect staged evidence before approving a catalogue record.</p>
      </div>
      {session && <button type="button" className="button-secondary" onClick={lock}>Lock review</button>}
    </header>
    {session ? <ReviewQueue accessKey={session.accessKey} initialQueue={session.queue} onLock={lock} /> : (
      <section className="review-unlock" aria-labelledby="review-unlock-heading">
        <h2 id="review-unlock-heading">Unlock local review</h2>
        <p>Enter the access key configured for this local backend.</p>
        <form onSubmit={unlock} autoComplete="off">
          <label className="review-control">
            <span>Local access key</span>
            <input ref={keyField} type="password" value={keyInput} onChange={(event) => setKeyInput(event.target.value)}
              required autoComplete="off" spellCheck={false} disabled={unlocking} />
          </label>
          {feedback && <p role="alert" className="review-inline-error">{feedback}</p>}
          <button type="submit" disabled={unlocking}>{unlocking ? 'Unlocking…' : 'Unlock review'}</button>
        </form>
      </section>
    )}
  </div>
}

function ReviewQueue({ accessKey, initialQueue, onLock }: {
  accessKey: string
  initialQueue: ReviewSummary[]
  onLock: () => void
}) {
  const [queue, setQueue] = useState(initialQueue)
  const [selected, setSelected] = useState(queue[0]?.draft_id)
  const [reviewer, setReviewer] = useState('')
  const reviewerInput = useRef<HTMLInputElement>(null)
  const active = queue.find((item) => item.draft_id === selected)
  const pending = queue.filter((item) => ['pending_review', 'needs_more_evidence'].includes(item.state)).length

  return <div className="review-layout">
    <section className="review-queue" aria-labelledby="review-queue-heading">
      <div className="review-queue-header">
        <h2 id="review-queue-heading">Review queue</h2>
        <p>{pending} open · {queue.length} total</p>
      </div>
      {queue.length > 0 ? <ul>
        {queue.map((draft) => <li key={draft.draft_id}>
          <button type="button" onClick={() => setSelected(draft.draft_id)} aria-pressed={active === draft}>
            <span className="review-queue-name">{heading(draft)}</span>
            <span className="review-queue-source">{sourceHost(draft.official_source_url)}</span>
            <StateBadge draft={draft} />
          </button>
        </li>)}
      </ul> : <p className="review-queue-empty">No drafts in this queue.</p>}
    </section>
    {active && <div className="review-workspace">
      <div className="review-identity">
        <label className="review-control">
          <span>Reviewer name or ID</span>
          <input ref={reviewerInput} value={reviewer} onChange={(event) => setReviewer(event.target.value)}
            maxLength={100} aria-describedby="review-identity-hint" />
        </label>
        <p id="review-identity-hint">Your identifier and rationale are recorded with each decision.</p>
      </div>
      <DraftWorkspace key={active.draft_id} summary={active} accessKey={accessKey} reviewer={reviewer}
        onReviewerNeeded={() => reviewerInput.current?.focus()} onLock={onLock}
        onUpdate={(detail) => setQueue((current) => current.map((item) => item.draft_id === detail.draft_id ? detail : item))} />
    </div>}
  </div>
}

function DraftWorkspace({ summary, accessKey, reviewer, onReviewerNeeded, onLock, onUpdate }: {
  summary: ReviewSummary
  accessKey: string
  reviewer: string
  onReviewerNeeded: () => void
  onLock: () => void
  onUpdate: (detail: ReviewDetail) => void
}) {
  const id = summary.draft_id
  const loader = useCallback(async (signal: AbortSignal) => {
    try {
      return await loadReviewDraft(id, accessKey, signal)
    } catch (error) {
      if (!signal.aborted && error instanceof ReviewRequestError && error.status === 401) onLock()
      throw error
    }
  }, [id, accessKey, onLock])
  const { resource, retry } = useResource(id, loader)
  const [updated, setUpdated] = useState<ReviewDetail>()
  const [message, setMessage] = useState<{ error: boolean; text: string; focus?: boolean }>()
  const [busy, setBusy] = useState(false)
  const pending = useRef<AbortController | null>(null)
  const feedback = useRef<HTMLParagraphElement>(null)

  useEffect(() => () => pending.current?.abort(), [])

  async function save(action: string, values: object, success: string) {
    if (pending.current) return false
    if (!reviewer.trim()) {
      setMessage({ error: true, text: 'Enter your reviewer name or ID before saving a decision.' })
      onReviewerNeeded()
      return false
    }
    const request = new AbortController()
    pending.current = request
    setBusy(true)
    setMessage(undefined)
    try {
      const detail = await submitReview(id, action, { ...values, reviewer: reviewer.trim() }, accessKey, request.signal)
      if (request.signal.aborted) return false
      setUpdated(detail)
      onUpdate(detail)
      setMessage({ error: false, text: success })
      return true
    } catch (error) {
      if (request.signal.aborted) return false
      if (error instanceof ReviewRequestError && error.status === 401) onLock()
      else setMessage({ error: true, text: errorMessage(error), focus: true })
      return false
    } finally {
      pending.current = null
      if (!request.signal.aborted) setBusy(false)
    }
  }

  useEffect(() => { if (message?.focus) feedback.current?.focus() }, [message])

  if (resource.status === 'loading') return <LoadingState>Loading the staged draft…</LoadingState>
  if (resource.status === 'error') return <ErrorState message={resource.message} retry={retry} />
  const draft = updated ?? resource.data
  const canEdit = draft.state === 'pending_review' || draft.state === 'needs_more_evidence'

  return <article className="review-draft" aria-labelledby="review-draft-heading">
    <header className="review-draft-header">
      <StateBadge draft={draft} />
      <h2 id="review-draft-heading">{heading(draft)}</h2>
      <div className="review-provenance">
        <SourceLink url={draft.draft.official_source_url} />
        <span>Retrieved {calendarDate(draft.draft.retrieved_on)}</span>
        <span>{draft.source_kind === 'manual' ? 'Manual source excerpt' : draft.source_kind === 'fixture' ? 'Fixture source' : 'Collected source excerpt'}</span>
      </div>
    </header>
    {message && <p ref={feedback} tabIndex={-1} role={message.error ? 'alert' : 'status'}
      className={message.error ? 'review-inline-error review-feedback' : 'review-feedback'}>{message.text}</p>}
    <DraftAlerts draft={draft} />
    <details className="review-disclosure">
      <summary>Read staged source excerpt</summary>
      <div className="review-disclosure-body review-source-text">{draft.source_text}</div>
    </details>
    <ReviewEvidence draft={draft} canEdit={canEdit} busy={busy}
      onSave={(field, values) => save('fields/' + field, values, fieldLabel(field) + ' decision saved.')} />
    <StipendEvidence draft={draft} />
    <DraftGates draft={draft} canEdit={canEdit} busy={busy} onSave={save} />
    <ReviewHistory draft={draft} />
  </article>
}

function DraftAlerts({ draft }: { draft: ReviewDetail }) {
  return <>
    {!!draft.duplicate_candidates.length && <div className="review-inline-warning">
      <strong>Possible catalogue duplicate</strong>
      <ul>{draft.duplicate_candidates.map((item, index) => (
        <li key={index}>{item.name}{item.cycle && ' · ' + item.cycle}</li>
      ))}</ul>
    </div>}
    {!!draft.related_draft_ids.length && <p className="review-inline-warning">
      {draft.related_draft_ids.length} other staged {draft.related_draft_ids.length === 1 ? 'draft may' : 'drafts may'} describe this opportunity.
    </p>}
    {draft.expired_deadline && <p className="review-inline-warning">The extracted deadline has passed. Verify the cycle before accepting a deadline.</p>}
    {(draft.conflicts.length > 0 || draft.wording_checks.length > 0) && <details className="review-disclosure">
      <summary>Catalogue comparisons and conflicts</summary>
      <ul className="review-disclosure-body">
        {[...draft.conflicts, ...draft.wording_checks].map((item, index) => <li key={index}>
          <strong>{fieldLabel(item.field)}</strong>
          <p>Catalogue value {JSON.stringify(item.catalogue)}</p>
          <blockquote>{item.excerpt}</blockquote>
        </li>)}
      </ul>
    </details>}
  </>
}

type Save = (action: string, values: object, success: string) => Promise<boolean>

function DraftGates({ draft, canEdit, busy, onSave }: {
  draft: ReviewDetail; canEdit: boolean; busy: boolean; onSave: Save
}) {
  const remaining = requiredFields.filter((field) => draft.field_reviews[field.key]?.decision !== 'accepted')
  const conflict = draft.blocked_fields.some((field) => draft.field_reviews[field]?.decision === 'accepted')
  const disabled = !!remaining.length || conflict || draft.duplicate_candidates.length > 0 || draft.source_kind === 'fixture'

  return <section className="review-gates" aria-labelledby="review-gates-heading">
    <h3 id="review-gates-heading">Approval &amp; publication</h3>
    {draft.published_id !== null ? <p role="status">
      Published as catalogue record <a href={'#/scholarships/' + draft.published_id}>{draft.published_id}</a>.
    </p> : draft.state === 'approved' && draft.dashboard_approved ? <>
      <p>Field review is approved. Publication revalidates the evidence and checks for duplicates.</p>
      <ApprovedRecord draft={draft} />
      <ConfirmationForm key="publish" action="publish" busy={busy} onSave={onSave} />
    </> : draft.state === 'approved' ? <p>This draft was approved outside the dashboard. Its review history is available below.</p>
      : draft.state === 'rejected' ? <p>This draft was rejected. Its review history is available below.</p>
        : canEdit && <>
          <p>Accept these fields with exact supporting evidence. Other requirements may stay unknown.</p>
          <ul className="review-gate-list">
            {requiredFields.map((field) => <li key={field.key}>
              {field.label} <span>{remaining.includes(field) ? 'Pending' : 'Accepted'}</span>
            </li>)}
          </ul>
          {draft.source_kind === 'fixture' && <p className="review-inline-warning">Fixture drafts cannot be approved.</p>}
          {conflict && <p className="review-inline-warning">Resolve any previously accepted fields that now have conflicting evidence.</p>}
          {disabled ? <button type="button" disabled>Approve draft</button>
            : <ConfirmationForm key="approve" action="approve" busy={busy} onSave={onSave} />}
          <DispositionForm key={draft.state} busy={busy} onSave={onSave} />
        </>}
  </section>
}

function ApprovedRecord({ draft }: { draft: ReviewDetail }) {
  const approval = draft.history.findLast((entry) => entry.action === 'approved')?.approved_record
  if (!approval) return null
  const verified = typeof approval.last_verified_at === 'string' ? calendarDate(approval.last_verified_at) : null
  const ignored = ['official_source_url', 'last_verified_at', 'eligibility_rules']
  return <details className="review-disclosure">
    <summary>Inspect the approved record</summary>
    <div className="review-disclosure-body">
      <dl className="review-approved-record">
        {Object.entries(approval).filter(([field]) => !ignored.includes(field)).map(([field, value]) => (
          <div key={field}><dt>{fieldLabel(field)}</dt><dd>{value === null ? 'Unknown' : valueLabel(value)}</dd></div>
        ))}
      </dl>
      <p><SourceLink url={draft.official_source_url} />{verified && ' · Last verified ' + verified}</p>
    </div>
  </details>
}

function ConfirmationForm({ action, busy, onSave }: {
  action: 'approve' | 'publish'; busy: boolean; onSave: Save
}) {
  const [rationale, setRationale] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const approval = action === 'approve'

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (confirmed && rationale.trim()) await onSave(action, { rationale, confirm: true },
      approval ? 'Draft approved. Publication is a separate action.' : 'Reviewed record published.')
  }

  return <form className="review-action-form" onSubmit={submit}>
    <fieldset disabled={busy}>
      <label className="review-control">
        <span>{approval ? 'Approval rationale' : 'Publication rationale'}</span>
        <textarea rows={2} value={rationale} onChange={(event) => setRationale(event.target.value)} required maxLength={2000} />
      </label>
      <label className="review-check">
        <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} required />
        <span>{approval ? 'I checked the cited evidence for this draft' : 'Publish this reviewed record to the catalogue'}</span>
      </label>
      <button type="submit">{approval ? 'Approve draft' : 'Publish record'}</button>
    </fieldset>
  </form>
}

function DispositionForm({ busy, onSave }: { busy: boolean; onSave: Save }) {
  const [decision, setDecision] = useState('')
  const [rationale, setRationale] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (decision && rationale.trim() && await onSave('decision', { decision, rationale }, 'Draft decision saved.')) {
      setDecision('')
      setRationale('')
    }
  }

  return <details className="review-disposition">
    <summary>Request more evidence or reject</summary>
    <form className="review-action-form" onSubmit={submit}>
      <fieldset disabled={busy}>
        <label className="review-control">
          <span>Draft decision</span>
          <select value={decision} onChange={(event) => setDecision(event.target.value)} required>
            <option value="">Select a decision</option>
            <option value="needs_more_evidence">Request more evidence</option>
            <option value="rejected">Reject draft</option>
          </select>
        </label>
        <label className="review-control">
          <span>Draft rationale</span>
          <textarea rows={2} value={rationale} onChange={(event) => setRationale(event.target.value)} required maxLength={2000} />
        </label>
        <button type="submit" className="button-secondary">Save draft decision</button>
      </fieldset>
    </form>
  </details>
}

const actionLabels: Record<string, string> = {
  approved: 'Draft approved', rejected: 'Draft rejected', needs_more_evidence: 'Requested more evidence',
  published: 'Record published',
}

function ReviewHistory({ draft }: { draft: ReviewDetail }) {
  const events = [
    ...draft.history.map((item) => ({ ...item, title: actionLabels[item.action] ?? item.action })),
    ...draft.field_history.map((item) => ({ ...item, title: fieldLabel(item.field) + ' · ' + decisionLabels[item.decision] })),
  ].sort((left, right) => right.decided_at.localeCompare(left.decided_at))
  return <details className="review-disclosure review-history">
    <summary>Review history <span>{events.length}</span></summary>
    {events.length > 0 ? <ol className="review-disclosure-body">
      {events.map((entry, index) => <li key={index}>
        <strong>{entry.title}</strong>
        <p className="review-small">{entry.reviewer} · {auditDate(entry.decided_at)}</p>
        <p>{entry.rationale}</p>
        {'evidence' in entry && Array.isArray(entry.evidence) && entry.evidence.map(
          (span, index) => <blockquote key={index}>{span}</blockquote>,
        )}
      </li>)}
    </ol> : <p className="review-disclosure-body">No human decisions recorded.</p>}
  </details>
}

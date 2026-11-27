import { useState } from 'react'
import type { FormEvent } from 'react'
import type {
  FieldAudit, FieldDecision, FundingObservation, ReviewDetail, ReviewedValue,
} from '../review'
import { calendarDate } from '../display'
import { SourceLink } from './ui'

import { auditDate, decisionLabels, groups, valueLabel } from '../review'
import type { FieldDefinition, FieldKind } from '../review'

const possibleOrigins: Record<string, string> = {
  tuition_coverage: 'funding_type',
  living_stipend: 'funding_amount',
  minimum_gpa: 'gpa_requirement',
  gpa_scale: 'gpa_requirement',
  minimum_ielts: 'language_requirement',
}

interface FieldInput {
  decision: FieldDecision
  rationale: string
  value?: ReviewedValue
  evidence?: string[]
}

export default function ReviewEvidence({
  draft, canEdit, busy, onSave,
}: {
  draft: ReviewDetail
  canEdit: boolean
  busy: boolean
  onSave: (field: string, values: FieldInput) => Promise<boolean>
}) {
  const [section, setSection] = useState(0)
  const fields = groups[section].fields
  return (
    <section className="review-ledger" aria-labelledby="review-ledger-heading">
      <div className="review-ledger-title">
        <h3 id="review-ledger-heading">Field evidence</h3>
        <p>Check each excerpt against the source before accepting a value.</p>
      </div>
      <div className="review-filters" role="group" aria-label="Field categories">
        {groups.map((group, index) => (
          <button type="button" className="button-text" key={group.label}
            aria-pressed={section === index} onClick={() => setSection(index)}>
            {group.label}
          </button>
        ))}
      </div>
      <div className="review-field-list">
        {fields.map((field) => (
          <EvidenceField key={field.key} draft={draft} field={field} canEdit={canEdit} busy={busy}
            onSave={(values) => onSave(field.key, values)} />
        ))}
      </div>
    </section>
  )
}

function EvidenceField({
  draft, field, canEdit, busy, onSave,
}: {
  draft: ReviewDetail
  field: FieldDefinition
  canEdit: boolean
  busy: boolean
  onSave: (values: FieldInput) => Promise<boolean>
}) {
  const audit = draft.field_reviews[field.key]
  const quote = draft.draft.fields[field.key] ?? draft.draft.fields[possibleOrigins[field.key]]
  const blocked = draft.blocked_fields.includes(field.key)
  const ambiguous = draft.draft.ambiguous_fields?.includes(field.key)
  return (
    <details className="review-field">
      <summary>
        <span className="review-field-name">{field.label}</span>
        <span className="review-field-caption">
          {audit?.decision === 'accepted' ? valueLabel(audit.value) : quote?.quote || 'No extracted evidence'}
        </span>
        <span className={'badge review-badge ' + (
          blocked || ambiguous ? 'review-warning' : audit?.decision === 'accepted' ? 'review-success' :
            audit?.decision === 'rejected' ? 'review-danger' : ''
        )}>
          {blocked || ambiguous ? 'Needs reconciliation' : audit ? decisionLabels[audit.decision] : 'Unreviewed'}
        </span>
      </summary>
      <div className="review-field-body">
        {field.required && <p className="review-small">Required for draft approval</p>}
        {field.evidenceOnly && <p className="review-small">Observation for the review history</p>}
        {quote ? <figure className="review-quote">
          <figcaption>Extracted excerpt <span>Scope {quote.scope.replaceAll('_', ' ')}</span></figcaption>
          <blockquote>{quote.quote}</blockquote>
        </figure> : <p className="review-small">The extractor left this field unknown.</p>}
        {(blocked || ambiguous) && (
          <p className="review-inline-warning">Compare the underlying sources before relying on this field.</p>
        )}
        {audit && <section className="review-last" aria-label={'Latest decision for ' + field.label}>
          <p><strong>{decisionLabels[audit.decision]}</strong> by {audit.reviewer} · {auditDate(audit.decided_at)}</p>
          <p>{audit.rationale}</p>
          {audit.value !== null && <p><strong>Reviewed value</strong> {valueLabel(audit.value)}</p>}
          {audit.evidence.map((span, index) => <blockquote key={index}>{span}</blockquote>)}
        </section>}
        {canEdit && <DecisionForm
          key={audit?.decided_at ?? 'new'} field={field} audit={audit} quote={quote?.quote}
          blocked={blocked} busy={busy} onSave={onSave} />}
      </div>
    </details>
  )
}

function DecisionForm({
  field, audit, quote, blocked, busy, onSave,
}: {
  field: FieldDefinition
  audit?: FieldAudit
  quote?: string
  blocked: boolean
  busy: boolean
  onSave: (values: FieldInput) => Promise<boolean>
}) {
  const [decision, setDecision] = useState<FieldDecision | ''>(blocked && audit?.decision === 'accepted' ? '' : audit?.decision ?? '')
  const [value, setValue] = useState(Array.isArray(audit?.value) ? audit.value.join('\n') : String(audit?.value ?? ''))
  const [spans, setSpans] = useState(audit?.evidence.length ? audit.evidence : [''])
  const [rationale, setRationale] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!decision || !rationale.trim()) return
    if (decision === 'accepted') {
      const submittedValue = field.kind === 'list' ? value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
        : field.kind === 'number' ? Number(value) : value.trim()
      if (!value.trim() || spans.some((span) => !span.trim())) return
      await onSave({ decision, rationale, value: submittedValue, evidence: spans })
    } else {
      await onSave({ decision, rationale })
    }
  }

  return (
    <form aria-label={'Review ' + field.label} className="review-field-form" onSubmit={submit}>
      <fieldset disabled={busy}>
        <label className="review-control">
          <span>Decision</span>
          <select value={decision} onChange={(event) => setDecision(event.target.value as FieldDecision | '')} required>
            <option value="">Select a decision</option>
            <option value="accepted" disabled={blocked}>Accept</option>
            <option value="rejected">Reject</option>
            <option value="unresolved">Mark unresolved</option>
          </select>
        </label>
        {decision === 'accepted' && <>
          <label className="review-control">
            <span>Reviewed value</span>
            <ValueControl kind={field.kind} value={value} onChange={setValue} />
            {field.hint && <small>{field.hint}</small>}
            {field.evidenceOnly && <small>Use the exact source wording.</small>}
            {field.kind === 'list' && <small>Enter one value per line.</small>}
          </label>
          {spans.map((span, index) => (
            <label className="review-control" key={index}>
              <span>{index ? 'Additional source excerpt ' + index : 'Source excerpt'}</span>
              <textarea value={span} onChange={(event) => setSpans(spans.map(
                (item, position) => position === index ? event.target.value : item,
              ))} rows={2} maxLength={400} required />
            </label>
          ))}
          <div className="review-form-actions">
            {quote && <button className="button-text" type="button"
              onClick={() => setSpans((previous) => [quote, ...previous.slice(1)])}>
              Use extracted excerpt
            </button>}
            {spans.length < 8 && <button className="button-text" type="button"
              onClick={() => setSpans((previous) => [...previous, ''])}>Add excerpt</button>}
            {spans.length > 1 && <button className="button-text" type="button"
              onClick={() => setSpans((previous) => previous.slice(0, -1))}>Remove last excerpt</button>}
          </div>
        </>}
        <label className="review-control">
          <span>Field rationale</span>
          <textarea rows={2} maxLength={2000} value={rationale}
            onChange={(event) => setRationale(event.target.value)} required />
        </label>
        <button type="submit" className="button-secondary">Save field decision</button>
      </fieldset>
    </form>
  )
}

function ValueControl({ kind, value, onChange }: {
  kind: FieldKind
  value: string
  onChange: (value: string) => void
}) {
  if (kind === 'degree' || kind === 'funding') {
    const options = kind === 'degree'
      ? [['master', 'Master’s'], ['bachelor', 'Bachelor’s'], ['doctorate', 'Doctorate']]
      : [['fully_funded', 'Fully funded'], ['partially_funded', 'Partially funded']]
    return <select value={value} onChange={(event) => onChange(event.target.value)} required>
      <option value="">Select a verified value</option>
      {options.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select>
  }
  if (kind === 'list' || kind === 'text') {
    return <textarea value={value} onChange={(event) => onChange(event.target.value)}
      maxLength={5000} rows={2} required />
  }
  return <input type={kind} value={value} onChange={(event) => onChange(event.target.value)}
    {...(kind === 'number' ? { step: 'any', min: 0 } : {})} required />
}

export function StipendEvidence({ draft }: { draft: ReviewDetail }) {
  const observations = [...(draft.draft.funding_observations ?? []), ...(draft.supplemental_funding ?? [])]
  const conflicts = draft.funding_conflicts ?? []
  if (!observations.length && !draft.supplemental_funding_missing) return null
  return (
    <section className="review-stipends" aria-label="Stipend evidence">
      <h3>Stipend evidence</h3>
      {draft.supplemental_funding_missing && <p className="review-inline-warning">
        The local record of historical and current stipends is unavailable. Keep the amount unresolved.
      </p>}
      {conflicts.length > 0 && <p className="review-inline-warning">
        Funding evidence has conflicting figures. Confirm the relevant cycle and payment scope before accepting a stipend.
      </p>}
      <div className="review-stipend-grid">
        {observations.map((item, index) => <Stipend key={index} observation={item} />)}
      </div>
    </section>
  )
}

function Stipend({ observation }: { observation: FundingObservation }) {
  const { amount, currency, period, payment_scope, qualifier, cycle, publication_year, retrieved_on, quote, source_url } = observation
  const [whole, fraction] = String(amount).split('.')
  const amountLabel = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction ? '.' + fraction : '')
  return (
    <figure className="review-quote">
      <figcaption>
        {qualifier === 'exact' ? '' : qualifier.replaceAll('_', ' ') + ' '}
        {currency ?? 'Currency unconfirmed'} {amountLabel}
        {period === 'one_time' ? ' · One-time payment' : period ? ' per ' + period : ' · Period unconfirmed'}
      </figcaption>
      <p className="review-small">
        {cycle ? 'Intake ' + cycle : 'Intake unconfirmed'}
        {publication_year ? ' · Published ' + publication_year : ''}
        {payment_scope ? ' · ' + payment_scope.replaceAll('_', ' ') : ''}
      </p>
      <blockquote>{quote}</blockquote>
      <p className="review-small">
        <SourceLink url={source_url} label="Source for this observation" />
        {retrieved_on ? ' · Retrieved ' + calendarDate(retrieved_on) : ''}
      </p>
    </figure>
  )
}

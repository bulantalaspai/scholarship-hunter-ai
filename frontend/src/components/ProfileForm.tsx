import { useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { StudentProfile } from '../types'

type Props = {
  onSubmit: (profile: StudentProfile) => void
  initialProfile?: StudentProfile
  busy?: boolean
  submitLabel?: string
}

type FormValues = {
  nationality: string
  degree_level: string
  degree_completed: string
  field_of_study: string
  gpa: string
  gpa_scale: string
  ielts_overall: string
  intended_start_year: string
  funding_preference: string
}

type FieldName = keyof FormValues
type FormErrors = Partial<Record<FieldName, string>>

const degrees = [
  ['high_school', 'High school'],
  ['associate', 'Associate degree'],
  ['bachelor', 'Bachelor’s degree'],
  ['master', 'Master’s degree'],
  ['doctorate', 'Doctorate'],
  ['other', 'Other qualification'],
] as const

function optionalNumber(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}
  for (const name of ['nationality', 'field_of_study'] as const) {
    if (!values[name].trim()) errors[name] = 'Enter this information.'
    else if (values[name].trim().length > 300)
      errors[name] = 'Use 300 characters or fewer.'
  }
  if (!degrees.some(([value]) => value === values.degree_level)) {
    errors.degree_level = 'Choose your current or completed degree level.'
  }
  if (!['unknown', 'true', 'false'].includes(values.degree_completed)) {
    errors.degree_completed = 'Choose a degree completion status.'
  }
  if (!['fully_funded', 'any_funding'].includes(values.funding_preference)) {
    errors.funding_preference = 'Choose the funding you would consider.'
  }

  const gpa = optionalNumber(values.gpa)
  const scale = optionalNumber(values.gpa_scale)
  if (gpa !== null && (!Number.isFinite(gpa) || gpa < 0)) {
    errors.gpa = 'Enter a finite GPA of zero or above.'
  }
  if (scale !== null && (!Number.isFinite(scale) || scale <= 0)) {
    errors.gpa_scale = 'Enter a finite GPA scale greater than zero.'
  }
  if (gpa !== null && scale === null)
    errors.gpa_scale = 'Enter the scale for this GPA.'
  if (gpa === null && scale !== null)
    errors.gpa = 'Enter your GPA or leave both GPA fields empty.'
  if (gpa !== null && scale !== null && gpa > scale) {
    errors.gpa = 'GPA cannot exceed its scale.'
  }

  const ielts = optionalNumber(values.ielts_overall)
  if (ielts !== null && (!Number.isFinite(ielts) || ielts < 0 || ielts > 9)) {
    errors.ielts_overall =
      'Enter an IELTS overall score between 0 and 9, or leave it empty.'
  }
  const year = Number(values.intended_start_year)
  if (
    !values.intended_start_year.trim() ||
    !Number.isInteger(year) ||
    year < 1900 ||
    year > 2200
  ) {
    errors.intended_start_year =
      'Enter a whole start year between 1900 and 2200.'
  }
  return errors
}

export default function ProfileForm({
  onSubmit,
  initialProfile,
  busy = false,
  submitLabel = 'Find my matches',
}: Props) {
  const id = useId()
  const formRef = useRef<HTMLFormElement>(null)
  const [values, setValues] = useState<FormValues>(() => ({
    nationality: initialProfile?.nationality ?? '',
    degree_level: initialProfile?.degree_level ?? '',
    degree_completed:
      initialProfile?.degree_completed == null
        ? 'unknown'
        : String(initialProfile.degree_completed),
    field_of_study: initialProfile?.field_of_study ?? '',
    gpa: initialProfile?.gpa == null ? '' : String(initialProfile.gpa),
    gpa_scale:
      initialProfile?.gpa_scale == null ? '' : String(initialProfile.gpa_scale),
    ielts_overall:
      initialProfile?.ielts_overall == null
        ? ''
        : String(initialProfile.ielts_overall),
    intended_start_year: String(
      initialProfile?.intended_start_year ?? new Date().getUTCFullYear() + 1,
    ),
    funding_preference: initialProfile?.funding_preference ?? '',
  }))
  const [errors, setErrors] = useState<FormErrors>({})

  useEffect(() => {
    if (Object.keys(errors).length > 0) {
      formRef.current
        ?.querySelector<HTMLInputElement | HTMLSelectElement>(
          '[aria-invalid="true"]',
        )
        ?.focus()
    }
  }, [errors])

  function update(name: FieldName, value: string) {
    setValues((previous) => ({ ...previous, [name]: value }))
  }

  function attributes(name: FieldName, hasHint = false) {
    const descriptions = [
      hasHint && `${id}-${name}-hint`,
      errors[name] && `${id}-${name}-error`,
    ].filter(Boolean)
    return {
      id: `${id}-${name}`,
      name,
      value: values[name],
      'aria-invalid': Boolean(errors[name]),
      'aria-describedby': descriptions.length
        ? descriptions.join(' ')
        : undefined,
      onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
        update(name, event.target.value),
    }
  }

  function error(name: FieldName) {
    return errors[name] ? (
      <p className="field-error" id={`${id}-${name}-error`}>
        {errors[name]}
      </p>
    ) : null
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const nextErrors = validate(values)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    onSubmit({
      nationality: values.nationality.trim(),
      degree_level: values.degree_level as StudentProfile['degree_level'],
      degree_completed:
        values.degree_completed === 'unknown'
          ? null
          : values.degree_completed === 'true',
      field_of_study: values.field_of_study.trim(),
      gpa: optionalNumber(values.gpa),
      gpa_scale: optionalNumber(values.gpa_scale),
      ielts_overall: optionalNumber(values.ielts_overall),
      intended_start_year: Number(values.intended_start_year),
      funding_preference:
        values.funding_preference as StudentProfile['funding_preference'],
    })
  }

  return (
    <form
      className="profile-form"
      ref={formRef}
      onSubmit={submit}
      noValidate
      autoComplete="off"
      aria-busy={busy}
    >
      {Object.keys(errors).length > 0 && (
        <div className="form-summary" role="alert">
          Please check the highlighted fields.
        </div>
      )}
      <fieldset className="form-section" disabled={busy}>
        <legend>Your academic background</legend>
        <p>
          Use the terms in the official requirements. Related fields and degree
          equivalence may need verification.
        </p>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={`${id}-nationality`}>Nationality</label>
            <input
              {...attributes('nationality', true)}
              type="text"
              required
              maxLength={300}
              placeholder="Country name"
            />
            <small id={`${id}-nationality-hint`}>
              Use the country name, for example Kazakhstan.
            </small>
            {error('nationality')}
          </div>
          <div className="field">
            <label htmlFor={`${id}-degree_level`}>Degree level</label>
            <select {...attributes('degree_level')} required>
              <option value="">Choose a qualification</option>
              {degrees.map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
            {error('degree_level')}
          </div>
          <div className="field">
            <label htmlFor={`${id}-degree_completed`}>Degree completion</label>
            <select {...attributes('degree_completed', true)}>
              <option value="unknown">Not specified</option>
              <option value="true">Completed</option>
              <option value="false">Currently studying</option>
            </select>
            <small id={`${id}-degree_completed-hint`}>
              An unfinished degree needs confirmation of completion timing.
            </small>
            {error('degree_completed')}
          </div>
          <div className="field">
            <label htmlFor={`${id}-field_of_study`}>Field of study</label>
            <input
              {...attributes('field_of_study')}
              type="text"
              required
              maxLength={300}
              placeholder="Your academic field"
            />
            {error('field_of_study')}
          </div>
        </div>
      </fieldset>
      <fieldset className="form-section" disabled={busy}>
        <legend>Grades and language evidence</legend>
        <p>
          Optional. Unknown scores stay unknown. We do not convert between GPA
          scales.
        </p>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={`${id}-gpa`}>GPA</label>
            <input
              {...attributes('gpa')}
              type="number"
              min="0"
              step="any"
              inputMode="decimal"
              placeholder="Optional"
            />
            {error('gpa')}
          </div>
          <div className="field">
            <label htmlFor={`${id}-gpa_scale`}>GPA scale</label>
            <input
              {...attributes('gpa_scale', true)}
              type="number"
              min="0"
              step="any"
              inputMode="decimal"
              placeholder="Optional"
            />
            <small id={`${id}-gpa_scale-hint`}>
              Enter the maximum of your grading scale.
            </small>
            {error('gpa_scale')}
          </div>
          <div className="field">
            <label htmlFor={`${id}-ielts_overall`}>IELTS overall</label>
            <input
              {...attributes('ielts_overall', true)}
              type="number"
              min="0"
              max="9"
              step="any"
              inputMode="decimal"
              placeholder="Optional"
            />
            <small id={`${id}-ielts_overall-hint`}>
              Alternative tests, exemptions, and component scores require
              separate verification.
            </small>
            {error('ielts_overall')}
          </div>
        </div>
      </fieldset>
      <fieldset className="form-section" disabled={busy}>
        <legend>Your plans</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={`${id}-intended_start_year`}>
              Intended start year
            </label>
            <input
              {...attributes('intended_start_year')}
              type="number"
              min="1900"
              max="2200"
              step="1"
              inputMode="numeric"
              required
            />
            {error('intended_start_year')}
          </div>
          <div className="field">
            <label htmlFor={`${id}-funding_preference`}>
              Funding preference
            </label>
            <select {...attributes('funding_preference')} required>
              <option value="">Choose a funding preference</option>
              <option value="fully_funded">Fully funded only</option>
              <option value="any_funding">Full or partial funding</option>
            </select>
            {error('funding_preference')}
          </div>
        </div>
      </fieldset>
      <p className="privacy-note">
        No account or identity documents are needed. Your profile is used for
        this check and is not saved by the application. Refreshing clears it.
      </p>
      <div className="form-actions">
        <button type="submit" disabled={busy}>
          {busy ? 'Checking your profile…' : submitLabel}
        </button>
      </div>
    </form>
  )
}

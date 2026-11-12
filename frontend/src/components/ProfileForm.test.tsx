import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { StudentProfile } from '../types'
import ProfileForm from './ProfileForm'

const validProfile: StudentProfile = {
  nationality: 'Kazakhstan',
  degree_level: 'bachelor',
  degree_completed: true,
  field_of_study: 'Computer Science',
  gpa: 3.5,
  gpa_scale: 4,
  ielts_overall: 7,
  intended_start_year: 2027,
  funding_preference: 'fully_funded',
}

describe('ProfileForm', () => {
  it('collects the required profile without identity or contact information', () => {
    render(<ProfileForm onSubmit={vi.fn()} />)
    for (const name of [
      'Nationality',
      'Degree level',
      'Degree completion',
      'Field of study',
      'GPA',
      'GPA scale',
      'IELTS overall',
      'Intended start year',
      'Funding preference',
    ]) {
      expect(screen.getByLabelText(name, { exact: true })).toBeVisible()
    }
    expect(
      screen.queryByLabelText(/name|email|password/i),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText('Degree completion')).toHaveValue('unknown')
    expect(screen.getByText(/not saved by the application/)).toBeVisible()
  })

  it('submits a trimmed profile with numeric scores and the selected completion status', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <ProfileForm
        onSubmit={onSubmit}
        initialProfile={{
          ...validProfile,
          nationality: ' Kazakhstan ',
          field_of_study: ' Computer Science ',
        }}
        submitLabel="Check eligibility"
      />,
    )
    await user.selectOptions(
      screen.getByLabelText('Degree completion'),
      'false',
    )
    await user.click(screen.getByRole('button', { name: 'Check eligibility' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      ...validProfile,
      degree_completed: false,
    })
  })

  it('preserves zero scores and unknown completion instead of converting them to blanks or true', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <ProfileForm
        onSubmit={onSubmit}
        initialProfile={{
          ...validProfile,
          gpa: 0,
          ielts_overall: 0,
          degree_completed: null,
        }}
      />,
    )
    expect(screen.getByLabelText('GPA', { exact: true })).toHaveValue(0)
    expect(screen.getByLabelText('IELTS overall')).toHaveValue(0)
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      ...validProfile,
      gpa: 0,
      ielts_overall: 0,
      degree_completed: null,
    })
  })

  it('leaves optional GPA, scale, and IELTS as null', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <ProfileForm
        onSubmit={onSubmit}
        initialProfile={{
          ...validProfile,
          gpa: null,
          gpa_scale: null,
          ielts_overall: null,
        }}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      ...validProfile,
      gpa: null,
      gpa_scale: null,
      ielts_overall: null,
    })
  })

  it('shows accessible errors and focuses the first invalid field', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<ProfileForm onSubmit={onSubmit} />)
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Please check the highlighted fields.',
    )
    expect(screen.getByLabelText('Nationality')).toHaveFocus()
    expect(screen.getByLabelText('Nationality')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    expect(screen.getByLabelText('Nationality')).toHaveAccessibleDescription(
      /Enter this information/,
    )
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it.each([
    ['GPA', '5', 'GPA cannot exceed its scale.'],
    ['GPA', '-1', 'Enter a finite GPA of zero or above.'],
    ['GPA scale', '0', 'Enter a finite GPA scale greater than zero.'],
    [
      'IELTS overall',
      '10',
      'Enter an IELTS overall score between 0 and 9, or leave it empty.',
    ],
    [
      'IELTS overall',
      '-1',
      'Enter an IELTS overall score between 0 and 9, or leave it empty.',
    ],
    [
      'Intended start year',
      '2027.5',
      'Enter a whole start year between 1900 and 2200.',
    ],
    [
      'Intended start year',
      '1899',
      'Enter a whole start year between 1900 and 2200.',
    ],
    [
      'Intended start year',
      '2201',
      'Enter a whole start year between 1900 and 2200.',
    ],
  ])('validates %s when the value is %s', async (label, value, message) => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<ProfileForm onSubmit={onSubmit} initialProfile={validProfile} />)
    const field = screen.getByLabelText(label, { exact: true })
    await user.clear(field)
    await user.type(field, value)
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    expect(screen.getByText(message)).toBeVisible()
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it.each([
    ['GPA scale', 'Enter the scale for this GPA.'],
    ['GPA', 'Enter your GPA or leave both GPA fields empty.'],
  ])(
    'requires the other GPA field when %s is cleared',
    async (label, message) => {
      const onSubmit = vi.fn()
      const user = userEvent.setup()
      render(<ProfileForm onSubmit={onSubmit} initialProfile={validProfile} />)
      await user.clear(screen.getByLabelText(label, { exact: true }))
      await user.click(screen.getByRole('button', { name: 'Find my matches' }))
      expect(screen.getByText(message)).toBeVisible()
      expect(onSubmit).not.toHaveBeenCalled()
    },
  )

  it('permits fractional grading scales without an arbitrary conversion', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <ProfileForm
        onSubmit={onSubmit}
        initialProfile={{
          ...validProfile,
          gpa: 2.2,
          gpa_scale: 2.5,
          funding_preference: 'any_funding',
        }}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      ...validProfile,
      gpa: 2.2,
      gpa_scale: 2.5,
      funding_preference: 'any_funding',
    })
  })

  it('clears validation errors on a successful corrected submission', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <ProfileForm
        onSubmit={onSubmit}
        initialProfile={{ ...validProfile, nationality: ' ' }}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    await user.clear(screen.getByLabelText('Nationality'))
    await user.type(screen.getByLabelText('Nationality'), 'Kazakhstan')
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith(validProfile)
  })

  it('disables controls and prevents submissions while a check is in progress', () => {
    render(
      <ProfileForm onSubmit={vi.fn()} initialProfile={validProfile} busy />,
    )
    expect(screen.getByLabelText('Nationality')).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Checking your profile…' }),
    ).toBeDisabled()
  })
})
